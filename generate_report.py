"""
generate_report.py
Reads data/price_history.csv (built up over multiple scraper.py runs) and
produces:
  - reports/dashboard.html   (interactive HTML dashboard, Chart.js)
  - reports/latest_report.pdf (static PDF snapshot, for sharing/printing)

Run this after scraper.py. It is safe to run even with only one week of
data — some sections will just show flat/first-run values.
"""

import os
from datetime import datetime, timezone

import qrcode
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
)

BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "data", "price_history.csv")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
CHART_TMP_DIR = os.path.join(BASE_DIR, "data", "_chart_tmp")


def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_FILE, parse_dates=["run_timestamp"])
    df["run_date"] = df["run_timestamp"].dt.date
    return df


def compute_insights(df: pd.DataFrame) -> dict:
    latest_date = df["run_date"].max()
    latest = df[df["run_date"] == latest_date]

    run_dates = sorted(df["run_date"].unique())
    insights = {
        "latest_date": latest_date,
        "num_runs": len(run_dates),
        "num_products_tracked": df["title"].nunique(),
        "avg_price_latest": round(latest["price_gbp"].mean(), 2),
        "out_of_stock_count": int((~latest["in_stock"]).sum()),
        "avg_rating_latest": round(latest["rating"].mean(), 2),
    }

    # Biggest price movers (only meaningful with 2+ runs)
    movers = pd.DataFrame()
    if len(run_dates) >= 2:
        first_date, last_date = run_dates[0], run_dates[-1]
        first = df[df["run_date"] == first_date].set_index("title")["price_gbp"]
        last = df[df["run_date"] == last_date].set_index("title")["price_gbp"]
        joined = pd.concat([first, last], axis=1, keys=["first_price", "last_price"]).dropna()
        joined["change"] = joined["last_price"] - joined["first_price"]
        joined["pct_change"] = (joined["change"] / joined["first_price"] * 100).round(1)
        movers = joined.reindex(joined["change"].abs().sort_values(ascending=False).index).head(10)

    insights["movers"] = movers
    return insights

def make_qr_code() -> str:
    os.makedirs(CHART_TMP_DIR, exist_ok=True)
    dashboard_url = "https://ompatel21599.github.io/price-monitoring-pipeline/"
    qr_path = os.path.join(CHART_TMP_DIR, "dashboard_qr.png")

    img = qrcode.make(dashboard_url)
    img.save(qr_path)

    return qr_path

def make_charts(df: pd.DataFrame) -> dict:
    os.makedirs(CHART_TMP_DIR, exist_ok=True)
    paths = {}

    # Chart 1: Average price over time
    avg_by_date = df.groupby("run_date")["price_gbp"].mean()
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.plot(avg_by_date.index.astype(str), avg_by_date.values, marker="o", color="#2563eb")
    ax.set_title("Average Price Over Time (£)")
    ax.set_ylabel("Avg price (£)")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    p1 = os.path.join(CHART_TMP_DIR, "avg_price_trend.png")
    fig.savefig(p1, dpi=150)
    plt.close(fig)
    paths["avg_price_trend"] = p1

    # Chart 2: Rating distribution (latest run)
    latest_date = df["run_date"].max()
    latest = df[df["run_date"] == latest_date]
    rating_counts = latest["rating"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.bar(rating_counts.index.astype(str), rating_counts.values, color="#16a34a")
    ax.set_title("Rating Distribution (Latest Run)")
    ax.set_xlabel("Star rating")
    ax.set_ylabel("Number of products")
    fig.tight_layout()
    p2 = os.path.join(CHART_TMP_DIR, "rating_distribution.png")
    fig.savefig(p2, dpi=150)
    plt.close(fig)
    paths["rating_distribution"] = p2

    # Chart 3: Stock availability over time
    stock_by_date = df.groupby("run_date")["in_stock"].mean() * 100
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.plot(stock_by_date.index.astype(str), stock_by_date.values, marker="o", color="#ea580c")
    ax.set_title("In-Stock Rate Over Time (%)")
    ax.set_ylabel("% in stock")
    ax.set_ylim(0, 105)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    p3 = os.path.join(CHART_TMP_DIR, "stock_rate_trend.png")
    fig.savefig(p3, dpi=150)
    plt.close(fig)
    paths["stock_rate_trend"] = p3

    return paths


def generate_html(df: pd.DataFrame, insights: dict) -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)

    avg_by_date = df.groupby("run_date")["price_gbp"].mean().round(2)
    labels = [str(d) for d in avg_by_date.index]
    values = [float(v) for v in avg_by_date.values]

    movers = insights["movers"]
    movers_rows = ""
    if not movers.empty:
        for title, row in movers.iterrows():
            direction = "📉" if row["change"] < 0 else "📈"
            movers_rows += f"""
            <tr>
                <td>{title}</td>
                <td>£{row['first_price']:.2f}</td>
                <td>£{row['last_price']:.2f}</td>
                <td>{direction} {row['pct_change']}%</td>
            </tr>"""
    else:
        movers_rows = "<tr><td colspan='4'>Need at least 2 scrape runs to show price movers.</td></tr>"

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Electronics-Store Price Monitor Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0f172a;
    --card: #1e293b;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --accent: #3b82f6;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 32px;
  }}
  h1 {{ margin-bottom: 4px; }}
  .subtitle {{ color: var(--muted); margin-top: 0; margin-bottom: 28px; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }}
  .kpi {{
    background: var(--card);
    border-radius: 12px;
    padding: 18px 20px;
    border: 1px solid #334155;
  }}
  .kpi .label {{ color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; }}
  .kpi .value {{ font-size: 28px; font-weight: 700; margin-top: 6px; }}
  .charts {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 20px;
    margin-bottom: 32px;
  }}
  .chart-card {{
    background: var(--card);
    border-radius: 12px;
    padding: 20px;
    border: 1px solid #334155;
  }}
  .chart-card h3 {{ margin-top: 0; color: var(--text); font-size: 15px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: var(--card);
    border-radius: 12px;
    overflow: hidden;
  }}
  th, td {{
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid #334155;
    font-size: 14px;
  }}
  th {{ color: var(--muted); text-transform: uppercase; font-size: 12px; letter-spacing: 0.05em; }}
  footer {{ color: var(--muted); margin-top: 32px; font-size: 13px; }}
</style>
</head>
<body>
  <h1>📊 Product Price Monitoring Dashboard</h1>
  <p class="subtitle">Automated weekly price &amp; availability tracking · Generated {generated_at}</p>

  <div class="grid">
    <div class="kpi"><div class="label">Products Tracked</div><div class="value">{insights['num_products_tracked']}</div></div>
    <div class="kpi"><div class="label">Scrape Runs</div><div class="value">{insights['num_runs']}</div></div>
    <div class="kpi"><div class="label">Avg Price (Latest)</div><div class="value">£{insights['avg_price_latest']}</div></div>
    <div class="kpi"><div class="label">Out of Stock (Latest)</div><div class="value">{insights['out_of_stock_count']}</div></div>
    <div class="kpi"><div class="label">Avg Rating (Latest)</div><div class="value">{insights['avg_rating_latest']} / 5</div></div>
  </div>

  <div class="charts">
    <div class="chart-card">
      <h3>Average Price Over Time</h3>
      <canvas id="priceTrendChart"></canvas>
    </div>
  </div>

  <h3>Biggest Price Movers (First Run vs Latest Run)</h3>
  <table>
    <thead>
      <tr><th>Product</th><th>First Price</th><th>Latest Price</th><th>Change</th></tr>
    </thead>
    <tbody>
      {movers_rows}
    </tbody>
  </table>

  <footer>
    Data source: books.toscrape.com (public scraping sandbox) · Pipeline runs weekly via GitHub Actions ·
    This project demonstrates an automated data collection → analysis → reporting pipeline.
  </footer>

<script>
  const ctx = document.getElementById('priceTrendChart');
  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: {labels},
      datasets: [{{
        label: 'Avg price (£)',
        data: {values},
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,0.15)',
        fill: true,
        tension: 0.3
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ labels: {{ color: '#e2e8f0' }} }} }},
      scales: {{
        x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }},
        y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }}
      }}
    }}
  }});
</script>
</body>
</html>
"""
    out_path = os.path.join(REPORTS_DIR, "dashboard.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out_path}")


def generate_pdf(df: pd.DataFrame, insights: dict, chart_paths: dict) -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    out_path = os.path.join(REPORTS_DIR, "latest_report.pdf")

    doc = SimpleDocTemplate(out_path, pagesize=letter,
                             topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=20)
    muted_style = ParagraphStyle("Muted", parent=styles["Normal"], textColor=colors.grey)

    story = []
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    story.append(Paragraph("Product Price Monitoring Report", title_style))
    story.append(Paragraph(f"Generated {generated_at}", muted_style))
    story.append(Spacer(1, 12))

    qr_path = make_qr_code()
    story.append(RLImage(qr_path, width=1.3 * inch, height=1.3 * inch))
    story.append(Paragraph("Scan to open the live interactive dashboard", muted_style))
    story.append(Spacer(1, 16))

    kpi_data = [
        ["Products Tracked", "Scrape Runs", "Avg Price (Latest)", "Out of Stock", "Avg Rating"],
        [
            str(insights["num_products_tracked"]),
            str(insights["num_runs"]),
            f"£{insights['avg_price_latest']}",
            str(insights["out_of_stock_count"]),
            f"{insights['avg_rating_latest']} / 5",
        ],
    ]
    kpi_table = Table(kpi_data, hAlign="LEFT")
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Average Price Trend", styles["Heading2"]))
    story.append(RLImage(chart_paths["avg_price_trend"], width=5.5 * inch, height=2.9 * inch))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Rating Distribution (Latest Run)", styles["Heading2"]))
    story.append(RLImage(chart_paths["rating_distribution"], width=5.5 * inch, height=2.9 * inch))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Stock Availability Trend", styles["Heading2"]))
    story.append(RLImage(chart_paths["stock_rate_trend"], width=5.5 * inch, height=2.9 * inch))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Biggest Price Movers", styles["Heading2"]))
    movers = insights["movers"]
    if not movers.empty:
        rows = [["Product", "First £", "Latest £", "% Change"]]
        for title, row in movers.iterrows():
            short_title = (title[:40] + "…") if len(title) > 40 else title
            rows.append([short_title, f"{row['first_price']:.2f}", f"{row['last_price']:.2f}", f"{row['pct_change']}%"])
        movers_table = Table(rows, hAlign="LEFT", colWidths=[3 * inch, 1 * inch, 1 * inch, 1 * inch])
        movers_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(movers_table)
    else:
        story.append(Paragraph("Need at least 2 scrape runs to show price movers.", styles["Normal"]))

    doc.build(story)
    print(f"Wrote {out_path}")


def main():
    if not os.path.isfile(DATA_FILE):
        raise SystemExit(
            f"No data found at {DATA_FILE}. Run scraper.py first to collect at least one snapshot."
        )

    df = load_data()
    insights = compute_insights(df)
    chart_paths = make_charts(df)

    generate_html(df, insights)
    generate_pdf(df, insights, chart_paths)


if __name__ == "__main__":
    main()