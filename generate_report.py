"""
generate_report.py
Reads data/price_history.csv (built up over multiple scraper.py runs) and
produces:
  - reports/dashboard.html   (interactive HTML dashboard, Chart.js)
  - reports/latest_report.pdf (static PDF snapshot, for sharing/printing)
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
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
)

from ml_analysis import build_ml_summary

BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "data", "price_history.csv")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
CHART_TMP_DIR = os.path.join(BASE_DIR, "data", "_chart_tmp")

DASHBOARD_URL = "https://ompatel21599.github.io/price-monitoring-pipeline/"


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

    top_expensive = latest.nlargest(10, "price_gbp")[["title", "price_gbp", "category"]]
    top_cheap = latest.nsmallest(10, "price_gbp")[["title", "price_gbp", "category"]]
    insights["top_expensive"] = top_expensive
    insights["top_cheap"] = top_cheap

    category_summary = latest.groupby("category")["price_gbp"].agg(["mean", "count"]).round(2)
    category_summary = category_summary.sort_values("mean", ascending=False)
    insights["category_summary"] = category_summary

    return insights


# ---------------------------------------------------------------------------
# Matplotlib chart styling (used for the PDF only — HTML uses Chart.js)
# ---------------------------------------------------------------------------
PDF_BG = "#ffffff"
PDF_PANEL = "#f4f6f8"
PDF_TEXT = "#1a1a1a"
PDF_MUTED = "#6b7280"
PDF_GOLD = "#b8862f"
PDF_TEAL = "#2d6e6e"
PDF_RED = "#a83e37"
PDF_GRID = "#e2e5e9"


def _style_ax(fig, ax, title):
    fig.patch.set_facecolor(PDF_BG)
    ax.set_facecolor(PDF_BG)
    ax.set_title(title, color=PDF_TEXT, fontsize=11, fontfamily="monospace", loc="left")
    ax.tick_params(colors=PDF_MUTED, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(PDF_GRID)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, color=PDF_GRID, linewidth=0.6, axis="y")
    ax.set_axisbelow(True)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_color(PDF_MUTED)


def make_charts(df: pd.DataFrame) -> dict:
    os.makedirs(CHART_TMP_DIR, exist_ok=True)
    paths = {}
    latest_date = df["run_date"].max()
    latest = df[df["run_date"] == latest_date]

    # Chart 1: Average price over time
    avg_by_date = df.groupby("run_date")["price_gbp"].mean()
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.plot(avg_by_date.index.astype(str), avg_by_date.values, marker="o",
            color=PDF_GOLD, linewidth=2, markersize=5)
    _style_ax(fig, ax, "AVG PRICE OVER TIME (£)")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    p1 = os.path.join(CHART_TMP_DIR, "avg_price_trend.png")
    fig.savefig(p1, dpi=150, facecolor=PDF_BG)
    plt.close(fig)
    paths["avg_price_trend"] = p1

    # Chart 2: Rating distribution
    rating_counts = latest["rating"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.bar(rating_counts.index.astype(str), rating_counts.values, color=PDF_TEAL)
    _style_ax(fig, ax, "RATING DISTRIBUTION")
    fig.tight_layout()
    p2 = os.path.join(CHART_TMP_DIR, "rating_distribution.png")
    fig.savefig(p2, dpi=150, facecolor=PDF_BG)
    plt.close(fig)
    paths["rating_distribution"] = p2

    # Chart 3: Stock availability over time
    stock_by_date = df.groupby("run_date")["in_stock"].mean() * 100
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.plot(stock_by_date.index.astype(str), stock_by_date.values, marker="o",
            color=PDF_TEAL, linewidth=2, markersize=5)
    _style_ax(fig, ax, "IN-STOCK RATE OVER TIME (%)")
    ax.set_ylim(0, 105)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    p3 = os.path.join(CHART_TMP_DIR, "stock_rate_trend.png")
    fig.savefig(p3, dpi=150, facecolor=PDF_BG)
    plt.close(fig)
    paths["stock_rate_trend"] = p3

    # Chart 4: Category price comparison
    cat_avg = latest.groupby("category")["price_gbp"].mean().sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.barh(cat_avg.index.astype(str), cat_avg.values, color=PDF_GOLD)
    _style_ax(fig, ax, "AVG PRICE BY CATEGORY (£)")
    ax.grid(True, color=PDF_GRID, linewidth=0.6, axis="x")
    fig.tight_layout()
    p4 = os.path.join(CHART_TMP_DIR, "category_price.png")
    fig.savefig(p4, dpi=150, facecolor=PDF_BG)
    plt.close(fig)
    paths["category_price"] = p4

    # Chart 5: Price distribution histogram (properly binned)
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.hist(latest["price_gbp"], bins=12, color=PDF_GOLD, edgecolor=PDF_BG)
    _style_ax(fig, ax, "PRICE DISTRIBUTION (£)")
    fig.tight_layout()
    p5 = os.path.join(CHART_TMP_DIR, "price_histogram.png")
    fig.savefig(p5, dpi=150, facecolor=PDF_BG)
    plt.close(fig)
    paths["price_histogram"] = p5

    # Chart 6: Stock status donut
    in_stock_count = int(latest["in_stock"].sum())
    out_stock_count = int((~latest["in_stock"]).sum())
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.pie(
        [in_stock_count, out_stock_count],
        labels=["In Stock", "Out of Stock"],
        colors=[PDF_TEAL, PDF_RED],
        autopct="%1.0f%%",
        startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": PDF_BG},
        textprops={"color": PDF_TEXT, "fontsize": 9},
    )
    ax.set_title("STOCK STATUS", color=PDF_TEXT, fontsize=11, fontfamily="monospace")
    fig.patch.set_facecolor(PDF_BG)
    fig.tight_layout()
    p6 = os.path.join(CHART_TMP_DIR, "stock_donut.png")
    fig.savefig(p6, dpi=150, facecolor=PDF_BG)
    plt.close(fig)
    paths["stock_donut"] = p6

    return paths


def make_ml_charts(df: pd.DataFrame, ml_summary: dict) -> dict:
    """Charts specific to the ML findings: anomaly scatter and forecast lines."""
    os.makedirs(CHART_TMP_DIR, exist_ok=True)
    paths = {}

    # Anomaly scatter: all latest-run products, colored by flagged/not
    latest_date = df["run_date"].max()
    latest = df[df["run_date"] == latest_date].reset_index(drop=True)
    anomalies = ml_summary["anomalies"]
    flagged_titles = set(anomalies["title"]) if not anomalies.empty else set()

    fig, ax = plt.subplots(figsize=(6.6, 3.0))
    colors_list = [PDF_RED if t in flagged_titles else PDF_TEAL for t in latest["title"]]
    sizes = [55 if t in flagged_titles else 22 for t in latest["title"]]
    ax.scatter(range(len(latest)), latest["price_gbp"], c=colors_list, s=sizes, alpha=0.85,
               edgecolors=PDF_BG, linewidths=0.5)
    _style_ax(fig, ax, "PRICE BY PRODUCT — ANOMALIES HIGHLIGHTED (LATEST RUN)")
    ax.set_xticks([])
    ax.set_ylabel("Price (£)", color=PDF_MUTED, fontsize=8)
    fig.tight_layout()
    p1 = os.path.join(CHART_TMP_DIR, "anomaly_scatter.png")
    fig.savefig(p1, dpi=150, facecolor=PDF_BG)
    plt.close(fig)
    paths["anomaly_scatter"] = p1

    # Forecast chart: actual vs projected for top forecasted products
    forecasts = ml_summary["forecasts"]
    if not forecasts.empty:
        run_dates = sorted(df["run_date"].unique())
        fig, ax = plt.subplots(figsize=(6.6, 3.2))
        palette = [PDF_GOLD, PDF_TEAL, "#8a6bbf", "#c96f3e", "#4f8fcf"]
        for i, title in enumerate(forecasts["title"].head(5)):
            series = df[df["title"] == title].sort_values("run_date")
            x_actual = list(range(len(series)))
            y_actual = series["price_gbp"].values
            color = palette[i % len(palette)]
            ax.plot(x_actual, y_actual, marker="o", color=color, linewidth=1.8,
                     markersize=4, label=title[:22])
            forecast_row = forecasts[forecasts["title"] == title].iloc[0]
            ax.plot([x_actual[-1], len(x_actual)], [y_actual[-1], forecast_row["forecast_price"]],
                     linestyle="--", color=color, linewidth=1.5, alpha=0.7)
            ax.scatter([len(x_actual)], [forecast_row["forecast_price"]], color=color,
                        marker="D", s=35, zorder=5)
        _style_ax(fig, ax, "FORECAST — TOP MOVERS (SOLID = ACTUAL, DASHED = PROJECTED)")
        ax.set_ylabel("Price (£)", color=PDF_MUTED, fontsize=8)
        ax.set_xticks(range(len(run_dates) + 1))
        ax.set_xticklabels([str(d) for d in run_dates] + ["next"], rotation=30, fontsize=7)
        legend = ax.legend(loc="upper left", fontsize=6.5, facecolor=PDF_PANEL,
                            edgecolor=PDF_GRID, labelcolor=PDF_TEXT)
        fig.tight_layout()
        p2 = os.path.join(CHART_TMP_DIR, "forecast_lines.png")
        fig.savefig(p2, dpi=150, facecolor=PDF_BG)
        plt.close(fig)
        paths["forecast_lines"] = p2

    return paths


def make_qr_code() -> str:
    os.makedirs(CHART_TMP_DIR, exist_ok=True)
    qr_path = os.path.join(CHART_TMP_DIR, "dashboard_qr.png")
    img = qrcode.make(DASHBOARD_URL)
    img.save(qr_path)
    return qr_path


def generate_html(df: pd.DataFrame, insights: dict) -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)

    avg_by_date = df.groupby("run_date")["price_gbp"].mean().round(2)
    labels = [str(d) for d in avg_by_date.index]
    values = [float(v) for v in avg_by_date.values]

    latest_date = df["run_date"].max()
    latest = df[df["run_date"] == latest_date]

    cat_avg = latest.groupby("category")["price_gbp"].mean().round(2).sort_values(ascending=False)
    cat_labels = [str(c) for c in cat_avg.index]
    cat_values = [float(v) for v in cat_avg.values]

    # Properly binned histogram data
    hist_series = pd.cut(latest["price_gbp"], bins=12)
    hist_counts = hist_series.value_counts().sort_index()
    price_bin_labels = [f"£{interval.left:.0f}-{interval.right:.0f}" for interval in hist_counts.index]
    price_bin_values = [int(v) for v in hist_counts.values]

    in_stock_count = int(latest["in_stock"].sum())
    out_stock_count = int((~latest["in_stock"]).sum())

    movers = insights["movers"]
    movers_rows = ""
    if not movers.empty:
        for title, row in movers.iterrows():
            direction = "▼" if row["change"] < 0 else "▲"
            color = "#3f8f8f" if row["change"] < 0 else "#d4a537"
            movers_rows += f"""
            <tr>
                <td>{title}</td>
                <td>£{row['first_price']:.2f}</td>
                <td>£{row['last_price']:.2f}</td>
                <td style="color:{color}">{direction} {row['pct_change']}%</td>
            </tr>"""
    else:
        movers_rows = "<tr><td colspan='4' class='empty-note'>Awaiting second scrape run for comparison data.</td></tr>"

    top_expensive_rows = "".join(
        f"<tr><td>{row['title']}</td><td>{row['category']}</td><td>£{row['price_gbp']:.2f}</td></tr>"
        for _, row in insights["top_expensive"].iterrows()
    )
    top_cheap_rows = "".join(
        f"<tr><td>{row['title']}</td><td>{row['category']}</td><td>£{row['price_gbp']:.2f}</td></tr>"
        for _, row in insights["top_cheap"].iterrows()
    )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Price Monitor — Analyst Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0b0f14;
    --panel: #11161d;
    --panel-2: #151b23;
    --text: #e8e6e0;
    --muted: #8a8f98;
    --gold: #d4a537;
    --teal: #3f8f8f;
    --red: #c1554d;
    --border: #212933;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: 'Inter', -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 0 0 60px;
  }}
  .mono {{ font-family: 'IBM Plex Mono', monospace; }}

  header {{
    border-bottom: 1px solid var(--border);
    padding: 28px 40px 20px;
  }}
  .eyebrow {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.12em;
    color: var(--gold);
    text-transform: uppercase;
    margin-bottom: 8px;
  }}
  h1 {{ margin: 0 0 6px; font-size: 26px; font-weight: 800; letter-spacing: -0.01em; }}
  .subtitle {{ color: var(--muted); font-size: 13px; font-family: 'IBM Plex Mono', monospace; }}

  .ticker {{
    display: flex;
    gap: 0;
    border-bottom: 1px solid var(--border);
    overflow-x: auto;
  }}
  .ticker-item {{
    flex: 1;
    min-width: 150px;
    padding: 18px 24px;
    border-right: 1px solid var(--border);
  }}
  .ticker-item:last-child {{ border-right: none; }}
  .ticker-label {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 6px;
  }}
  .ticker-value {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 24px;
    font-weight: 600;
    color: var(--text);
  }}
  .ticker-value.gold {{ color: var(--gold); }}
  .ticker-value.teal {{ color: var(--teal); }}
  .ticker-value.red {{ color: var(--red); }}

  main {{ padding: 0 40px; max-width: 1360px; margin: 0 auto; }}

  .section-label {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--gold);
    margin: 48px 0 16px;
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  .section-label::after {{
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }}

  .panel {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 20px 22px;
  }}
  .panel h3 {{
    margin: 0 0 16px;
    font-size: 13px;
    font-weight: 600;
    color: var(--muted);
    font-family: 'IBM Plex Mono', monospace;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}

  .grid-1 {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .grid-donut {{ display: grid; grid-template-columns: 340px 1fr; gap: 16px; align-items: stretch; }}
  @media (max-width: 820px) {{
    .grid-2, .grid-donut {{ grid-template-columns: 1fr; }}
    header, main {{ padding-left: 20px; padding-right: 20px; }}
  }}

  table {{ width: 100%; border-collapse: collapse; }}
  th {{
    text-align: left;
    padding: 10px 14px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
  }}
  td {{
    padding: 10px 14px;
    font-size: 13.5px;
    border-bottom: 1px solid var(--border);
  }}
  tr:last-child td {{ border-bottom: none; }}
  .empty-note {{ color: var(--muted); font-style: italic; font-size: 13px; }}

  footer {{
    margin-top: 60px;
    padding: 24px 40px;
    border-top: 1px solid var(--border);
    color: var(--muted);
    font-size: 12px;
    font-family: 'IBM Plex Mono', monospace;
    text-align: center;
  }}
  footer a {{ color: var(--gold); text-decoration: none; }}
</style>
</head>
<body>

  <header>
    <div class="eyebrow">Automated Market Intelligence</div>
    <h1>Product Price Monitor</h1>
    <div class="subtitle">books.toscrape.com sample · Last updated {generated_at}</div>
  </header>

  <div class="ticker">
    <div class="ticker-item">
      <div class="ticker-label">Products Tracked</div>
      <div class="ticker-value">{insights['num_products_tracked']}</div>
    </div>
    <div class="ticker-item">
      <div class="ticker-label">Scrape Runs</div>
      <div class="ticker-value">{insights['num_runs']}</div>
    </div>
    <div class="ticker-item">
      <div class="ticker-label">Avg Price</div>
      <div class="ticker-value gold">£{insights['avg_price_latest']}</div>
    </div>
    <div class="ticker-item">
      <div class="ticker-label">Out of Stock</div>
      <div class="ticker-value {'red' if insights['out_of_stock_count'] > 0 else ''}">{insights['out_of_stock_count']}</div>
    </div>
    <div class="ticker-item">
      <div class="ticker-label">Avg Rating</div>
      <div class="ticker-value teal">{insights['avg_rating_latest']}/5</div>
    </div>
  </div>

  <main>

    <div class="section-label">Trend</div>
    <div class="grid-1">
      <div class="panel">
        <h3>Average Price Over Time</h3>
        <canvas id="priceTrendChart" height="80"></canvas>
      </div>
    </div>

    <div class="section-label">Category &amp; Distribution</div>
    <div class="grid-2">
      <div class="panel">
        <h3>Average Price by Category</h3>
        <canvas id="categoryChart"></canvas>
      </div>
      <div class="panel">
        <h3>Price Distribution</h3>
        <canvas id="priceHistChart"></canvas>
      </div>
    </div>

    <div class="section-label">Availability</div>
    <div class="grid-donut">
      <div class="panel" style="display:flex; flex-direction:column;">
        <h3>Stock Status — Latest Run</h3>
        <div style="flex:1; display:flex; align-items:center; justify-content:center;">
          <canvas id="stockDonutChart"></canvas>
        </div>
      </div>
      <div class="panel">
        <h3>In-Stock Rate Over Time</h3>
        <canvas id="stockTrendChart"></canvas>
      </div>
    </div>

    <div class="section-label">Price Movement</div>
    <div class="panel" style="padding:0;">
      <table>
        <thead><tr><th>Product</th><th>First Run</th><th>Latest Run</th><th>Change</th></tr></thead>
        <tbody>{movers_rows}</tbody>
      </table>
    </div>

    <div class="section-label">Top 10 — Most &amp; Least Expensive</div>
    <div class="grid-2">
      <div class="panel" style="padding:0;">
        <table>
          <thead><tr><th>Product</th><th>Category</th><th>Price</th></tr></thead>
          <tbody>{top_expensive_rows}</tbody>
        </table>
      </div>
      <div class="panel" style="padding:0;">
        <table>
          <thead><tr><th>Product</th><th>Category</th><th>Price</th></tr></thead>
          <tbody>{top_cheap_rows}</tbody>
        </table>
      </div>
    </div>

  </main>

  <footer>
    DATA SOURCE: books.toscrape.com (public scraping sandbox) &nbsp;·&nbsp; PIPELINE: GitHub Actions, weekly &nbsp;·&nbsp;
    <a href="https://github.com/ompatel21599/price-monitoring-pipeline">View source</a>
  </footer>

  <div id="subscribeModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.65); z-index:1000; align-items:center; justify-content:center;">
    <div style="background:#11161d; border:1px solid #212933; border-radius:8px; padding:28px; max-width:380px; width:90%; font-family:'Inter',sans-serif;">
      <h3 style="margin-top:0; font-family:'IBM Plex Mono',monospace; font-size:15px; color:#d4a537; letter-spacing:0.02em;">GET THE WEEKLY PDF REPORT</h3>
      <p style="color:#8a8f98; font-size:13.5px; line-height:1.5;">Enter your email to receive this price monitoring report automatically every week.</p>
      <input id="subscribeEmail" type="email" placeholder="you@example.com"
             style="width:100%; padding:10px 12px; border-radius:5px; border:1px solid #212933; background:#0b0f14; color:#e8e6e0; margin-bottom:12px; box-sizing:border-box; font-family:'IBM Plex Mono',monospace; font-size:13px;">
      <div id="subscribeMsg" style="font-size:12.5px; margin-bottom:12px; font-family:'IBM Plex Mono',monospace;"></div>
      <div style="display:flex; gap:10px;">
        <button onclick="submitSubscribe()" style="flex:1; padding:10px; border-radius:5px; border:none; background:#d4a537; color:#0b0f14; cursor:pointer; font-weight:700; font-family:'IBM Plex Mono',monospace; font-size:12.5px; letter-spacing:0.04em;">SUBSCRIBE</button>
        <button onclick="closeSubscribeModal()" style="flex:1; padding:10px; border-radius:5px; border:1px solid #212933; background:transparent; color:#8a8f98; cursor:pointer; font-family:'IBM Plex Mono',monospace; font-size:12.5px;">NOT NOW</button>
      </div>
    </div>
  </div>

<script>
  Chart.defaults.font.family = "'IBM Plex Mono', monospace";
  Chart.defaults.color = '#8a8f98';

  new Chart(document.getElementById('priceTrendChart'), {{
    type: 'line',
    data: {{ labels: {labels}, datasets: [{{
      label: 'Avg price (£)', data: {values},
      borderColor: '#d4a537', backgroundColor: 'rgba(212,165,55,0.12)',
      fill: true, tension: 0.3, pointBackgroundColor: '#d4a537', pointRadius: 4
    }}] }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ticks: {{ color: '#8a8f98' }}, grid: {{ color: '#212933' }} }},
        y: {{ ticks: {{ color: '#8a8f98' }}, grid: {{ color: '#212933' }} }}
      }}
    }}
  }});

  new Chart(document.getElementById('categoryChart'), {{
    type: 'bar',
    data: {{ labels: {cat_labels}, datasets: [{{
      label: 'Avg price (£)', data: {cat_values}, backgroundColor: '#d4a537', borderRadius: 3
    }}] }},
    options: {{
      indexAxis: 'y',
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ticks: {{ color: '#8a8f98' }}, grid: {{ color: '#212933' }} }},
        y: {{ ticks: {{ color: '#8a8f98' }}, grid: {{ display: false }} }}
      }}
    }}
  }});

  new Chart(document.getElementById('priceHistChart'), {{
    type: 'bar',
    data: {{
      labels: {price_bin_labels},
      datasets: [{{ label: 'Products', data: {price_bin_values}, backgroundColor: '#3f8f8f', borderRadius: 3 }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ticks: {{ color: '#8a8f98', maxRotation: 45, minRotation: 45, font: {{ size: 10 }} }}, grid: {{ display: false }} }},
        y: {{ ticks: {{ color: '#8a8f98' }}, grid: {{ color: '#212933' }} }}
      }}
    }}
  }});

  new Chart(document.getElementById('stockDonutChart'), {{
    type: 'doughnut',
    data: {{
      labels: ['In Stock', 'Out of Stock'],
      datasets: [{{ data: [{in_stock_count}, {out_stock_count}], backgroundColor: ['#3f8f8f', '#c1554d'], borderColor: '#11161d', borderWidth: 3 }}]
    }},
    options: {{
      plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#8a8f98', font: {{ size: 11 }} }} }} }}
    }}
  }});

  new Chart(document.getElementById('stockTrendChart'), {{
    type: 'line',
    data: {{ labels: {labels}, datasets: [{{
      label: '% in stock', data: {[float(v) for v in (df.groupby("run_date")["in_stock"].mean()*100).round(1).values]},
      borderColor: '#3f8f8f', backgroundColor: 'rgba(63,143,143,0.12)', fill: true, tension: 0.3, pointBackgroundColor: '#3f8f8f', pointRadius: 4
    }}] }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ticks: {{ color: '#8a8f98' }}, grid: {{ color: '#212933' }} }},
        y: {{ min: 0, max: 105, ticks: {{ color: '#8a8f98' }}, grid: {{ color: '#212933' }} }}
      }}
    }}
  }});

  // --- Weekly PDF subscription popup ---
  const SUPABASE_URL = "https://opqsrqmkbvfzihvlfapp.supabase.co";
  const SUPABASE_KEY = "sb_publishable_9MajMK69FNeKARvRjisQ6w_d9ESJWV8";
  const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

  function showSubscribeModal() {{
    if (localStorage.getItem('subscribePromptShown') === 'true') return;
    document.getElementById('subscribeModal').style.display = 'flex';
  }}

  function closeSubscribeModal() {{
    document.getElementById('subscribeModal').style.display = 'none';
    localStorage.setItem('subscribePromptShown', 'true');
  }}

  async function submitSubscribe() {{
    const emailInput = document.getElementById('subscribeEmail');
    const msg = document.getElementById('subscribeMsg');
    const email = emailInput.value.trim();

    if (!email || !email.includes('@')) {{
      msg.style.color = '#c1554d';
      msg.textContent = 'Please enter a valid email.';
      return;
    }}

    msg.style.color = '#8a8f98';
    msg.textContent = 'Submitting...';

    const {{ error }} = await supabaseClient.from('subscribers').insert({{ email: email }});

    if (error) {{
      msg.style.color = '#c1554d';
      msg.textContent = error.message.includes('duplicate') ? 'Already subscribed.' : 'Something went wrong. Try again.';
    }} else {{
      msg.style.color = '#3f8f8f';
      msg.textContent = 'Subscribed — weekly PDF incoming.';
      setTimeout(closeSubscribeModal, 1500);
    }}
  }}

  setTimeout(showSubscribeModal, 1500);
</script>
</body>
</html>
"""
    out_path = os.path.join(REPORTS_DIR, "dashboard.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out_path}")


def build_headline(df: pd.DataFrame, insights: dict) -> str:
    latest_date = df["run_date"].max()
    latest = df[df["run_date"] == latest_date]
    cat_avg = latest.groupby("category")["price_gbp"].mean()
    top_category = cat_avg.idxmax()

    parts = [f"{top_category} leads category pricing at £{cat_avg.max():.2f} avg"]

    oos = insights["out_of_stock_count"]
    if oos > 0:
        parts.append(f"{oos} product{'s' if oos != 1 else ''} out of stock this run")
    else:
        parts.append("full availability across tracked products")

    movers = insights["movers"]
    if not movers.empty:
        biggest = movers.iloc[0]
        direction = "up" if biggest["change"] > 0 else "down"
        parts.append(f"biggest mover {direction} {abs(biggest['pct_change']):.1f}%")

    return " · ".join(parts) + "."


DOC_NAVY = colors.HexColor("#16324f")
DOC_GOLD = colors.HexColor("#b8862f")
DOC_TEAL = colors.HexColor("#2d6e6e")
DOC_RED = colors.HexColor("#a83e37")
DOC_TEXT = colors.HexColor("#1a1a1a")
DOC_MUTED = colors.HexColor("#6b7280")
DOC_LINE = colors.HexColor("#d9dde3")
DOC_PANEL = colors.HexColor("#f4f6f8")


def generate_pdf(df: pd.DataFrame, insights: dict, chart_paths: dict, ml_summary: dict) -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    out_path = os.path.join(REPORTS_DIR, "latest_report.pdf")

    NAVY = colors.HexColor("#1f3a5f")
    BLACK = colors.HexColor("#1a1a1a")
    GREY = colors.HexColor("#555555")
    LINE = colors.HexColor("#cccccc")

    doc = SimpleDocTemplate(out_path, pagesize=letter,
                             topMargin=0.85 * inch, bottomMargin=0.85 * inch,
                             leftMargin=0.9 * inch, rightMargin=0.9 * inch)

    title_style = ParagraphStyle("TitleCustom", fontName="Helvetica-Bold", fontSize=20,
                                  textColor=BLACK, spaceAfter=4, leading=24)
    subtitle_style = ParagraphStyle("Subtitle", fontName="Helvetica-Oblique", fontSize=10.5,
                                     textColor=GREY, spaceAfter=18)
    h1_style = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=13,
                               textColor=NAVY, spaceBefore=18, spaceAfter=8)
    h2_style = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=10.5,
                               textColor=BLACK, spaceBefore=10, spaceAfter=6)
    body_style = ParagraphStyle("Body", fontName="Helvetica", fontSize=10, leading=15,
                                 textColor=BLACK, spaceAfter=8, alignment=4)
    caption_style = ParagraphStyle("Caption", fontName="Helvetica-Oblique", fontSize=8.5,
                                    textColor=GREY, spaceAfter=10)
    header_text_style = ParagraphStyle("HeaderText", fontName="Helvetica", leading=16)

    generated_at = datetime.now(timezone.utc).strftime("%B %d, %Y — %H:%M UTC")
    qr_path = make_qr_code()

    latest_date = df["run_date"].max()
    latest = df[df["run_date"] == latest_date]
    n_products = insights["num_products_tracked"]
    n_runs = insights["num_runs"]
    anomalies = ml_summary["anomalies"]
    forecasts = ml_summary["forecasts"]

    def plain_table(rows, col_widths):
        t = Table(rows, hAlign="LEFT", colWidths=col_widths)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, BLACK),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, LINE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    story = []

    # ---------- Header with QR code top-right ----------
    header = Table(
        [[
            Paragraph(f"<b>Product Price Monitor</b><br/>"
                      f"<font size=10 color='#555555'><i>Machine Learning Analysis Report</i></font><br/>"
                      f"<font size=8.5 color='#777777'>Generated {generated_at}</font>",
                      header_text_style),
            RLImage(qr_path, width=0.75 * inch, height=0.75 * inch),
        ]],
        colWidths=[5.3 * inch, 0.9 * inch],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header)

    hr = Table([[""]], colWidths=[6.2 * inch], rowHeights=[1])
    hr.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.75, LINE)]))
    story.append(Spacer(1, 8))
    story.append(hr)
    story.append(Spacer(1, 10))

    # ---------- Executive summary ----------
    story.append(Paragraph("Executive Summary", h1_style))

    summary_text = (
        f"This report summarizes automated price monitoring across {n_products} tracked products "
        f"over {n_runs} scrape run{'s' if n_runs != 1 else ''}. Two machine learning techniques were "
        f"applied to the collected data: anomaly detection, to identify products priced unusually "
        f"relative to their category, and price forecasting, to project short-term price movement "
        f"based on historical trend. "
    )
    if not anomalies.empty:
        summary_text += (
            f"The analysis identified {len(anomalies)} product{'s' if len(anomalies) != 1 else ''} "
            f"with pricing that falls outside the expected range for its category. "
        )
    else:
        summary_text += "No pricing anomalies were identified in the most recent run. "

    if not forecasts.empty:
        summary_text += (
            f"Among products with sufficient history, {ml_summary['trending_up']} show an upward "
            f"price trend and {ml_summary['trending_down']} show a downward trend. {ml_summary['confidence_note']}"
        )
    else:
        summary_text += ml_summary["confidence_note"]

    story.append(Paragraph(summary_text, body_style))

    # ---------- Anomaly detection section ----------
    story.append(Paragraph("Anomaly Detection", h1_style))
    story.append(Paragraph(
        "Each product's latest price is compared against the mean and standard deviation of its "
        "own category, using a Z-score threshold of 1.5 standard deviations. To prevent a single "
        "extreme value from distorting its own baseline, each product is excluded from the "
        "calculation of its category's mean and standard deviation before being scored against it. "
        "This avoids a common statistical pitfall where an outlier masks itself by pulling the "
        "average toward its own value.",
        body_style
    ))

    if "anomaly_scatter" in chart_paths:
        story.append(RLImage(chart_paths["anomaly_scatter"], width=6.0 * inch, height=2.3 * inch))
        story.append(Paragraph(
            "Figure 1. Price by product for the latest scrape run. Each point represents one "
            "product; flagged anomalies are shown larger and in a distinct color.",
            caption_style
        ))

        # Data-driven explanation of what the chart shows
        cat_price_range = latest.groupby("category")["price_gbp"].agg(["min", "max"])
        widest_cat = cat_price_range.assign(range=lambda d: d["max"] - d["min"])["range"].idxmax()
        widest_range = cat_price_range.loc[widest_cat]
        chart1_explain = (
            f"Across the {latest['category'].nunique()} tracked categories, price spread varies "
            f"considerably: {widest_cat} shows the widest range in this run, from "
            f"£{widest_range['min']:.2f} to £{widest_range['max']:.2f}. "
        )
        if not anomalies.empty:
            top_anomaly = anomalies.iloc[0]
            chart1_explain += (
                f"The most significant anomaly is \u201c{top_anomaly['title']}\u201d, priced at "
                f"£{top_anomaly['price_gbp']:.2f} against a {top_anomaly['category']} category average "
                f"of £{top_anomaly['cat_mean']:.2f} — a Z-score of {top_anomaly['z_score']:.2f}, "
                f"placing it {top_anomaly['direction']} the expected range for its category."
            )
        else:
            chart1_explain += "No products in this run fell outside the ±1.5 standard deviation threshold."
        story.append(Paragraph(chart1_explain, body_style))

    if not anomalies.empty:
        rows = [["Product", "Category", "Price", "Category Avg", "Z-Score", "Direction"]]
        for _, row in anomalies.iterrows():
            title = (row["title"][:26] + "…") if len(row["title"]) > 26 else row["title"]
            rows.append([
                title, row["category"], f"£{row['price_gbp']:.2f}",
                f"£{row['cat_mean']:.2f}", f"{row['z_score']:.2f}", row["direction"].capitalize(),
            ])
        story.append(Spacer(1, 6))
        story.append(plain_table(rows, [1.8 * inch, 0.95 * inch, 0.75 * inch, 1.0 * inch, 0.75 * inch, 0.8 * inch]))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Table 1. All products flagged as anomalous in the latest run, ranked by absolute "
            "Z-score. A positive Z-score indicates a price above the category average; a negative "
            "value indicates a price below it.",
            caption_style
        ))
    else:
        story.append(Paragraph("No products exceeded the anomaly threshold in this run.", body_style))

    story.append(PageBreak())

    # ---------- Price forecast section ----------
    story.append(Paragraph("Price Forecast", h1_style))
    story.append(Paragraph(
        "A linear regression model is fit to each product's price history, using scrape run "
        "sequence as the independent variable, to project price for the next scheduled run. "
        "This is a simple trend-following method: it assumes the rate of change observed so far "
        f"will continue, and does not account for external market factors. {ml_summary['confidence_note']}",
        body_style
    ))

    if not forecasts.empty:
        if "forecast_lines" in chart_paths:
            story.append(RLImage(chart_paths["forecast_lines"], width=6.0 * inch, height=2.9 * inch))
            story.append(Paragraph(
                "Figure 2. Actual price history (solid lines) and projected next-period price "
                "(dashed lines, diamond marker) for the five products with the largest projected "
                "percentage change.",
                caption_style
            ))

            top_forecast = forecasts.iloc[0]
            direction_word = "increase" if top_forecast["trend"] == "up" else (
                "decrease" if top_forecast["trend"] == "down" else "remain flat"
            )
            chart2_explain = (
                f"The product with the largest projected movement is \u201c{top_forecast['title']}\u201d, "
                f"currently priced at £{top_forecast['current_price']:.2f} and projected to "
                f"{direction_word} to approximately £{top_forecast['forecast_price']:.2f} "
                f"({top_forecast['pct_change']:+.1f}%) by the next scrape run. "
            )
            if n_runs <= 2:
                chart2_explain += (
                    "With only a small number of historical points, this projection should be "
                    "treated as directional rather than precise — it will sharpen as more weekly "
                    "runs accumulate."
                )
            else:
                chart2_explain += (
                    f"This projection is based on {n_runs} historical data points per product and "
                    "reflects the linear trend observed to date."
                )
            story.append(Paragraph(chart2_explain, body_style))

        rows = [["Product", "Current Price", "Forecast Price", "Change", "Trend"]]
        for _, row in forecasts.iterrows():
            title = (row["title"][:28] + "…") if len(row["title"]) > 28 else row["title"]
            rows.append([
                title, f"£{row['current_price']:.2f}", f"£{row['forecast_price']:.2f}",
                f"{row['pct_change']}%", row["trend"].capitalize(),
            ])
        story.append(Spacer(1, 6))
        story.append(plain_table(rows, [2.2 * inch, 1.1 * inch, 1.1 * inch, 0.85 * inch, 0.85 * inch]))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Table 2. The five products with the largest projected price change, ranked by "
            "absolute percentage change.",
            caption_style
        ))
    else:
        story.append(Paragraph(
            "Forecasting requires at least two scrape runs and will populate automatically once "
            "additional data has been collected.",
            body_style
        ))

    story.append(PageBreak())

    # ---------- Reference charts with explanatory narrative ----------
    story.append(Paragraph("Reference Charts", h1_style))
    story.append(Paragraph(
        "The charts in this section summarize the underlying dataset used in the analysis above "
        "and are provided for additional context.",
        body_style
    ))

    avg_by_date = df.groupby("run_date")["price_gbp"].mean()
    trend_explain = f"Average price across all tracked products currently stands at £{insights['avg_price_latest']:.2f}. "
    if len(avg_by_date) >= 2:
        change = avg_by_date.iloc[-1] - avg_by_date.iloc[0]
        pct = (change / avg_by_date.iloc[0] * 100) if avg_by_date.iloc[0] else 0
        direction = "risen" if change > 0 else ("fallen" if change < 0 else "stayed flat")
        trend_explain += (
            f"Since the first recorded run, the overall average has {direction} by "
            f"£{abs(change):.2f} ({pct:+.1f}%)."
        )
    else:
        trend_explain += "This is the first recorded run; a trend line will appear once a second run has been collected."

    story.append(Paragraph("Average Price Over Time", h2_style))
    story.append(RLImage(chart_paths["avg_price_trend"], width=6.2 * inch, height=2.3 * inch))
    story.append(Paragraph(trend_explain, body_style))

    cat_avg = latest.groupby("category")["price_gbp"].mean().sort_values(ascending=False)
    cat_explain = (
        f"{cat_avg.index[0]} carries the highest average price in this run, at "
        f"£{cat_avg.iloc[0]:.2f}, while {cat_avg.index[-1]} is the lowest, at £{cat_avg.iloc[-1]:.2f}."
    )
    story.append(Paragraph("Average Price by Category", h2_style))
    story.append(RLImage(chart_paths["category_price"], width=6.2 * inch, height=2.3 * inch))
    story.append(Paragraph(cat_explain, body_style))

    story.append(PageBreak())

    hist_explain = (
        f"Prices in the latest run range from £{latest['price_gbp'].min():.2f} to "
        f"£{latest['price_gbp'].max():.2f}, with a median of £{latest['price_gbp'].median():.2f}. "
        "The distribution below shows how tracked products are spread across that range."
    )
    story.append(Paragraph("Price Distribution", h2_style))
    story.append(RLImage(chart_paths["price_histogram"], width=6.2 * inch, height=2.3 * inch))
    story.append(Paragraph(hist_explain, body_style))

    in_stock_count = int(latest["in_stock"].sum())
    out_stock_count = int((~latest["in_stock"]).sum())
    stock_explain = (
        f"Of the {n_products} products tracked in the latest run, {in_stock_count} are currently "
        f"in stock and {out_stock_count} are out of stock."
    )
    story.append(Paragraph("Stock Availability", h2_style))
    story.append(RLImage(chart_paths["stock_donut"], width=3.0 * inch, height=3.0 * inch))
    story.append(Paragraph(stock_explain, body_style))

    def on_later_pages(canvas_obj, doc_obj):
        width, height = letter
        canvas_obj.saveState()
        canvas_obj.setStrokeColor(LINE)
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(0.9 * inch, 0.6 * inch, width - 0.9 * inch, 0.6 * inch)
        canvas_obj.setFillColor(GREY)
        canvas_obj.setFont("Helvetica-Oblique", 8)
        canvas_obj.drawString(0.9 * inch, 0.45 * inch, "Product Price Monitor — ML Analysis Report")
        canvas_obj.drawRightString(width - 0.9 * inch, 0.45 * inch, f"Page {doc_obj.page}")
        canvas_obj.restoreState()

    doc.build(story, onLaterPages=on_later_pages)
    print(f"Wrote {out_path}")


def main():
    if not os.path.isfile(DATA_FILE):
        raise SystemExit(
            f"No data found at {DATA_FILE}. Run scraper.py first to collect at least one snapshot."
        )

    df = load_data()
    insights = compute_insights(df)
    chart_paths = make_charts(df)

    ml_summary = build_ml_summary(df)
    ml_chart_paths = make_ml_charts(df, ml_summary)
    chart_paths.update(ml_chart_paths)

    generate_html(df, insights)
    generate_pdf(df, insights, chart_paths, ml_summary)


if __name__ == "__main__":
    main()
