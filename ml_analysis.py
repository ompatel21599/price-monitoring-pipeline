"""
ml_analysis.py
Machine learning analysis layer for the price monitoring pipeline.

Two techniques, both chosen to be honest and explainable rather than
black-box, and both designed to degrade gracefully with limited history:

1. Anomaly detection — Z-score of each product's latest price relative to
   its category's mean/std. Works even with a single scrape run, since it
   compares across products within a run rather than across time.

2. Price forecasting — simple linear regression of each product's price
   over time, projecting the next period. Confidence is explicitly reported
   based on how many historical points exist; with fewer than 3 runs the
   forecast is flagged low-confidence rather than presented as reliable.

This module is intentionally decoupled from generate_report.py — it takes
a DataFrame in, returns plain dicts/DataFrames out, and has no knowledge
of HTML, PDF, or chart rendering.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


ANOMALY_Z_THRESHOLD = 1.5  # products beyond this many std-devs are flagged


def detect_price_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Z-score each product's latest price against its category's mean/std
    (within the latest scrape run). Each product is excluded from its own
    baseline calculation so a single extreme outlier can't mask itself by
    dragging the category mean/std toward it.
    """
    latest_date = df["run_date"].max()
    latest = df[df["run_date"] == latest_date].copy().reset_index(drop=True)

    z_scores = []
    for idx, row in latest.iterrows():
        same_cat_others = latest[
            (latest["category"] == row["category"]) & (latest.index != idx)
        ]["price_gbp"]

        if len(same_cat_others) < 2:
            z_scores.append(0.0)
            continue

        cat_mean = same_cat_others.mean()
        cat_std = same_cat_others.std()
        if not cat_std or np.isnan(cat_std):
            z_scores.append(0.0)
            continue

        z_scores.append((row["price_gbp"] - cat_mean) / cat_std)

    latest["z_score"] = z_scores
    latest["cat_mean"] = latest.groupby("category")["price_gbp"].transform(
        lambda s: s.mean()
    )

    flagged = latest[latest["z_score"].abs() >= ANOMALY_Z_THRESHOLD].copy()
    flagged["direction"] = np.where(flagged["z_score"] > 0, "above", "below")
    flagged = flagged.reindex(flagged["z_score"].abs().sort_values(ascending=False).index)

    return flagged[["title", "category", "price_gbp", "cat_mean", "z_score", "direction"]]


def forecast_prices(df: pd.DataFrame, top_n: int = 5) -> dict:
    """
    Fit a simple linear regression per product (price vs. run index) and
    project the next period's price. Returns a dict with:
      - 'forecasts': DataFrame of product, current price, projected price,
        trend direction, confidence level
      - 'confidence_note': human-readable caveat based on data volume
    Products are ranked by |projected change| and the top_n most notable
    are returned, but the confidence note applies pipeline-wide.
    """
    run_dates = sorted(df["run_date"].unique())
    n_runs = len(run_dates)
    date_to_idx = {d: i for i, d in enumerate(run_dates)}
    df = df.copy()
    df["run_idx"] = df["run_date"].map(date_to_idx)

    if n_runs < 2:
        return {
            "forecasts": pd.DataFrame(),
            "confidence_note": (
                "Only one scrape run available — forecasting requires at least "
                "two runs to establish a trend. Results will populate after the "
                "next scheduled run."
            ),
            "confidence_level": "insufficient_data",
        }

    results = []
    for title, group in df.groupby("title"):
        group = group.sort_values("run_idx")
        if len(group) < 2:
            continue
        X = group["run_idx"].values.reshape(-1, 1)
        y = group["price_gbp"].values

        model = LinearRegression()
        model.fit(X, y)
        next_idx = np.array([[group["run_idx"].max() + 1]])
        predicted = float(model.predict(next_idx)[0])
        current = float(group["price_gbp"].iloc[-1])
        change = predicted - current
        pct_change = (change / current * 100) if current else 0

        results.append({
            "title": title,
            "category": group["category"].iloc[-1],
            "current_price": round(current, 2),
            "forecast_price": round(max(predicted, 0), 2),
            "change": round(change, 2),
            "pct_change": round(pct_change, 1),
            "trend": "up" if change > 0.01 else ("down" if change < -0.01 else "flat"),
            "points_used": len(group),
        })

    forecasts = pd.DataFrame(results)
    if not forecasts.empty:
        forecasts = forecasts.reindex(
            forecasts["pct_change"].abs().sort_values(ascending=False).index
        ).head(top_n)

    if n_runs == 2:
        confidence_level = "low"
        confidence_note = (
            "Based on 2 scrape runs — enough for a directional trend, but not "
            "yet a reliable forecast. Confidence will improve with more history."
        )
    elif n_runs <= 4:
        confidence_level = "moderate"
        confidence_note = (
            f"Based on {n_runs} scrape runs — a reasonable short-term trend, "
            "though still limited history for high-confidence forecasting."
        )
    else:
        confidence_level = "reasonable"
        confidence_note = (
            f"Based on {n_runs} scrape runs — sufficient history for a "
            "reasonably confident short-term linear projection."
        )

    return {
        "forecasts": forecasts,
        "confidence_note": confidence_note,
        "confidence_level": confidence_level,
    }


def build_ml_summary(df: pd.DataFrame) -> dict:
    """
    Top-level entry point: runs both analyses and returns everything the
    report generator needs, plus a data-driven headline sentence.
    """
    anomalies = detect_price_anomalies(df)
    forecast_result = forecast_prices(df)
    forecasts = forecast_result["forecasts"]

    n_anomalies = len(anomalies)
    trending_up = int((forecasts["trend"] == "up").sum()) if not forecasts.empty else 0
    trending_down = int((forecasts["trend"] == "down").sum()) if not forecasts.empty else 0

    headline_parts = [f"{n_anomalies} price anomal{'y' if n_anomalies == 1 else 'ies'} detected"]
    if not forecasts.empty:
        headline_parts.append(f"{trending_up} products trending up, {trending_down} trending down")
    else:
        headline_parts.append("forecasting pending additional runs")

    return {
        "anomalies": anomalies,
        "forecasts": forecasts,
        "confidence_note": forecast_result["confidence_note"],
        "confidence_level": forecast_result["confidence_level"],
        "n_anomalies": n_anomalies,
        "trending_up": trending_up,
        "trending_down": trending_down,
        "headline": " · ".join(headline_parts) + ".",
    }
