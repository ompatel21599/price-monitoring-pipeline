\# 📊 Automated Product Price Monitoring Pipeline



An end-to-end data pipeline that scrapes product prices weekly, tracks price

history over time, and automatically generates an HTML dashboard and PDF

report — with zero manual steps after setup.



This project simulates a real competitor price-monitoring workflow that

retail and e-commerce analytics teams run in production, using

\[books.toscrape.com](https://books.toscrape.com) (a public scraping sandbox)

as the data source.



\## Why this project



Most portfolio projects stop at "I built a dashboard from a CSV I downloaded

once." This one shows the full lifecycle an analyst is actually responsible

for:



\- \*\*Data collection\*\* — a scraper that runs on a schedule, not a one-off script

\- \*\*Data history\*\* — prices are appended over time, not overwritten, so trends are real

\- \*\*Automation\*\* — GitHub Actions runs the whole pipeline weekly with no human involvement

\- \*\*Reporting for two audiences\*\* — an interactive HTML dashboard (for exploring)

&#x20; and a static PDF (for sharing with people who just want the summary)



\## How it works

