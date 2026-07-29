## What I built

An automated pipeline that scrapes product prices weekly, runs machine
learning on the results (anomaly detection + price forecasting), and
produces both a live interactive dashboard and a written PDF analysis
report — with zero manual steps after setup.

**Live dashboard:** https://ompatel21599.github.io/price-monitoring-pipeline/
**Repo:** you're already here 🙂
**Full case study:** [CASE_STUDY.md](../blob/main/CASE_STUDY.md)

## Why I built it this way

Most portfolio data projects stop at "download a CSV once, build a
dashboard." That shows charting skills, but not what an analyst actually
does — collecting data on an ongoing basis, watching it change, and
communicating findings to someone who won't read the code.

So this one:
- Scrapes on a real schedule (GitHub Actions, weekly) instead of a one-off script
- Appends price history instead of overwriting it, so trends are real
- Runs actual ML on the data (Z-score anomaly detection + linear regression
  forecasting) instead of just descriptive stats
- Outputs to two audiences: an interactive dashboard for exploring, and a
  written PDF report for sharing

## The most interesting bug

While testing the anomaly detector, I injected a deliberately extreme
price (£500 into a category averaging ~£30) to confirm it would get
flagged. It didn't.

Turned out the detector was including every product — including the
outlier itself — when calculating the category's mean and standard
deviation it was then compared against. The £500 value dragged the
average up and inflated the spread enough that its own z-score no longer
looked extreme. This is a real statistical trap called outlier masking.
The fix: exclude each product from its own category's baseline before
scoring it.

It's a small code change, but it only surfaces if you actually test
against a known-extreme value rather than trusting that "the math looks
right." Full writeup of this and a few other bugs (a missing
`</script>` tag that silently broke a popup, a histogram that wasn't
actually binning data, a duplicate-row crash that only showed up in CI)
is in the case study linked above.

## Tech stack

Python (requests, BeautifulSoup, pandas, scikit-learn, matplotlib,
reportlab), Chart.js, Supabase, GitHub Actions.

Happy to answer questions about any part of it — scraping approach, the
ML methodology, or the automation setup.
