\# 📊 Automated Price Monitoring Pipeline with ML-Driven Analysis



An end-to-end data pipeline that scrapes product prices weekly, applies

machine learning to detect anomalies and forecast trends, and automatically

generates an interactive dashboard and a written analysis report — with

zero manual steps after setup.



This project simulates a real competitor price-monitoring workflow that

retail and e-commerce analytics teams run in production, using

\[books.toscrape.com](https://books.toscrape.com) (a public scraping sandbox)

as the data source.



\*\*Live dashboard:\*\* https://ompatel21599.github.io/price-monitoring-pipeline/



\## Why this project



Most portfolio projects stop at "I built a dashboard from a CSV I downloaded

once." This one covers the full lifecycle an analyst is actually responsible

for — collection, storage, analysis, and communication:



\- \*\*Data collection\*\* — a scraper that runs on a schedule, not a one-off script

\- \*\*Data history\*\* — prices are appended over time, not overwritten, so trends are real

\- \*\*Machine learning analysis\*\* — anomaly detection and price forecasting, not just descriptive charts

\- \*\*Automation\*\* — GitHub Actions runs the whole pipeline weekly with no human involvement

\- \*\*Two audiences\*\* — an interactive HTML dashboard for exploring, and a written PDF report for sharing

\- \*\*Distribution\*\* — visitors can subscribe on the dashboard to receive the weekly PDF by email



\## How it works

GitHub Actions (weekly, Monday 06:00 UTC)

│

▼

scraper.py ──────► data/price\_history.csv (appends new snapshot)

│

▼

ml\_analysis.py

│ (anomaly detection + price forecasting)

▼

generate\_report.py

│

├──► reports/dashboard.html (interactive charts, Chart.js, email signup)

└──► reports/latest\_report.pdf (written ML analysis report, QR-linked to dashboard)

│

▼

Auto-committed back to the repo





\## Machine learning approach



\*\*Anomaly detection\*\* — each product's latest price is compared against its

category's mean and standard deviation using a Z-score threshold of 1.5.

Each product is excluded from its own category baseline before scoring, to

prevent a single extreme outlier from masking itself by skewing the average

it's being compared against.



\*\*Price forecasting\*\* — a linear regression is fit per product against

scrape-run sequence, projecting the next period's price. The report states

an explicit confidence level based on how much history is available, and

becomes more confident automatically as more weekly runs accumulate.



\## What gets tracked



For each product, every run captures: price (£), category, stock

availability, star rating, and timestamp.



\## Tech stack



| Purpose | Tool |

|---|---|

| Scraping | `requests` + `BeautifulSoup` |

| Data handling | `pandas` |

| Machine learning | `scikit-learn` (linear regression), NumPy (Z-score anomaly detection) |

| Charts (PDF) | `matplotlib` |

| Charts (dashboard) | `Chart.js` |

| PDF generation | `reportlab` |

| Email capture | Supabase (Postgres + REST API) |

| Scheduling | GitHub Actions (`cron`) |



\## Running it yourself



```bash

git clone https://github.com/ompatel21599/price-monitoring-pipeline.git

cd price-monitoring-pipeline

pip install -r requirements.txt



\# Collect a snapshot

python scraper.py



\# Run ML analysis and build the dashboard + PDF

python generate\_report.py

```



Open `reports/dashboard.html` in a browser, or view `reports/latest\_report.pdf`.



\## Automating it on your own repo



The workflow in `.github/workflows/weekly\_price\_check.yml` is already wired

up. Once you push this repo to GitHub:



1\. Go to \*\*Settings → Actions → General → Workflow permissions\*\* and enable

&#x20;  "Read and write permissions" (so the workflow can commit new data back).

2\. That's it — it'll run automatically every Monday, or you can trigger it

&#x20;  manually from the \*\*Actions\*\* tab (`Run workflow`).



\## Notes on the data source



`books.toscrape.com` is a site purpose-built for scraping practice — it

explicitly allows automated access, unlike most real retail sites, which

block scraping and prohibit it in their terms of service. The pipeline

architecture here is identical to what you'd point at a real product catalog

or internal pricing API in a production setting.



\## Possible extensions



\- Automatically email the weekly PDF to subscribers collected via the dashboard

\- Swap the CSV for a lightweight SQLite database as history grows

\- Add more ML techniques (clustering by price/rating pattern, seasonality detection)

