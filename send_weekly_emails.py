"""
send_weekly_emails.py
Reads all subscriber emails from Supabase and sends each one the latest
PDF report via Brevo, along with a short project intro and a link to
the GitHub Discussions tab for feedback.

Uses Brevo rather than Resend because Brevo's free tier allows sending to
arbitrary recipients without verifying a custom domain first - Resend's
free/sandbox tier restricts sending to only the account owner's verified
email, which isn't useful for real subscribers. See CASE_STUDY.md for the
full story of that discovery.

Uses plain HTTP requests rather than an SDK, to avoid adding an extra
dependency for a straightforward use case.

Required environment variables (set as GitHub Secrets in CI, or in your
local shell for testing):
  - SUPABASE_URL
  - SUPABASE_SERVICE_KEY   (service_role key — read access to subscribers)
  - BREVO_API_KEY
"""

import base64
import os
import sys

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")

PDF_PATH = os.path.join(os.path.dirname(__file__), "reports", "latest_report.pdf")
DASHBOARD_URL = "https://ompatel21599.github.io/price-monitoring-pipeline/"
DISCUSSIONS_URL = "https://github.com/ompatel21599/price-monitoring-pipeline/discussions"

# Brevo requires a sender identity, but unlike Resend does not require a
# verified custom domain to send to arbitrary recipients on the free tier.
FROM_NAME = "Price Monitor"
FROM_EMAIL = "pricepipeline.noreply@gmail.com"


def get_subscribers() -> list[str]:
    """Fetch all subscriber emails from Supabase using the service_role key."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variable.")

    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/subscribers",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        },
        params={"select": "email"},
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json()
    return [row["email"] for row in rows if row.get("email")]


def build_email_html(is_welcome: bool) -> str:
    intro = (
        "Thanks for subscribing! Here's your first weekly price monitoring report, "
        "attached as a PDF."
        if is_welcome else
        "Here's this week's price monitoring report, attached as a PDF."
    )
    return f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a;">
      <h2 style="margin-bottom: 4px;">📊 Product Price Monitor</h2>
      <p style="color: #555;">Automated weekly price &amp; availability tracking</p>
      <p>{intro}</p>
      <p>
        This project scrapes product prices on a weekly schedule, runs machine learning
        analysis (anomaly detection and price forecasting) on the results, and publishes
        both a live dashboard and this PDF report — fully automated, no manual steps.
      </p>
      <p>
        <a href="{DASHBOARD_URL}" style="color: #1f3a5f;">View the live interactive dashboard →</a>
      </p>
      <p>
        Have feedback, a question, or a feature you'd like to see? I'd genuinely like to hear it —
        <a href="{DISCUSSIONS_URL}" style="color: #1f3a5f;">leave a note on the GitHub Discussions page</a>.
      </p>
      <hr style="border: none; border-top: 1px solid #ddd; margin: 24px 0;">
      <p style="color: #999; font-size: 12px;">
        You're receiving this because you subscribed on the Price Monitor dashboard.
      </p>
    </div>
    """


def send_email(to_address: str, is_welcome: bool = False) -> bool:
    if not BREVO_API_KEY:
        raise SystemExit("Missing BREVO_API_KEY environment variable.")

    if not os.path.isfile(PDF_PATH):
        raise SystemExit(f"No PDF found at {PDF_PATH}. Run generate_report.py first.")

    with open(PDF_PATH, "rb") as f:
        pdf_bytes = f.read()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    subject = (
        "Welcome — your first Price Monitor report is attached"
        if is_welcome else
        "Your weekly Price Monitor report"
    )

    payload = {
        "sender": {"name": FROM_NAME, "email": FROM_EMAIL},
        "to": [{"email": to_address}],
        "subject": subject,
        "htmlContent": build_email_html(is_welcome),
        "attachment": [
            {
                "name": "price-monitor-report.pdf",
                "content": pdf_b64,
            }
        ],
    }

    resp = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json",
            "accept": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if resp.status_code >= 400:
        print(f"  FAILED for {to_address}: {resp.status_code} {resp.text}")
        return False

    print(f"  Sent to {to_address}")
    return True


def main():
    is_welcome = "--welcome" in sys.argv
    single_recipient = None
    for arg in sys.argv[1:]:
        if arg.startswith("--to="):
            single_recipient = arg.split("=", 1)[1]

    if single_recipient:
        print(f"Sending {'welcome' if is_welcome else 'weekly'} email to {single_recipient}...")
        send_email(single_recipient, is_welcome=is_welcome)
        return

    print("Fetching subscriber list from Supabase...")
    subscribers = get_subscribers()
    print(f"Found {len(subscribers)} subscriber(s).")

    if not subscribers:
        print("No subscribers to email. Done.")
        return

    sent, failed = 0, 0
    for email in subscribers:
        ok = send_email(email, is_welcome=False)
        if ok:
            sent += 1
        else:
            failed += 1

    print(f"Done. Sent: {sent}, Failed: {failed}")


if __name__ == "__main__":
    main()
