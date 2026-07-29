# Case Study: Building an Automated Price Monitoring Pipeline

This document walks through how this project was built, the decisions
behind it, and the real problems that came up along the way — including
the ones that weren't obvious at first.

**Live dashboard:** https://ompatel21599.github.io/price-monitoring-pipeline/

---

## The goal

Most portfolio data projects follow the same shape: download a CSV once,
build a dashboard, done. That's useful for showing charting skills, but it
doesn't show what an analyst actually does day to day — collecting data on
an ongoing basis, watching it change over time, and communicating findings
to someone who isn't going to read the code.

The goal here was to build something closer to a real internal tool: a
pipeline that collects data on its own schedule, applies real analysis to
it, and produces something a non-technical stakeholder could actually use —
without me touching it after setup.

## Architecture decisions

**Why scrape instead of use an API?**
Web scraping is a more common real-world constraint than clean APIs —
most competitor price-monitoring in retail *is* scraping, not an official
feed. `books.toscrape.com` was chosen deliberately over a real retailer:
it's a site built specifically for scraping practice and explicitly allows
automated access, whereas sites like Amazon actively block scrapers and
prohibit it in their terms of service. The scraping logic itself is
identical to what would point at a real catalog.

**Why append history instead of overwrite?**
A single scrape is a snapshot. The interesting analysis — price trends,
forecasting, "has this changed since last week" — only exists if past runs
are preserved. Every run appends to `data/price_history.csv` rather than
replacing it, which is what makes the trend charts and forecasting
meaningful rather than cosmetic.

**Why GitHub Actions for scheduling?**
It's free for public repos, requires no server to maintain, and the whole
point of the project was demonstrating *automation*, not just a script
that could theoretically be automated. The workflow runs weekly, scrapes,
re-analyzes, regenerates both outputs, and commits the results back to the
repo — no manual step after initial setup.

**Why two output formats (HTML dashboard + PDF)?**
They serve different audiences. The dashboard is for someone who wants to
explore the data interactively. The PDF is for someone who wants a
self-contained summary they can forward, print, or read without opening a
browser — which is why it was eventually rebuilt as a written report with
analysis, not just a printout of the same charts.

## Adding machine learning

The original version computed simple descriptive statistics — averages,
top 10 lists, category breakdowns. That's reporting, not analysis. Two ML
techniques were added to make the PDF genuinely analytical:

- **Anomaly detection** — Z-scoring each product's price against its
  category, to flag pricing that looks unusual
- **Price forecasting** — linear regression per product across scrape
  history, projecting the next period's price

Both were chosen deliberately over more "impressive-sounding" techniques
because they're *explainable*. A hiring manager (or anyone else) can
understand exactly what the model is doing and why, rather than trusting a
black box. That mattered more here than raw sophistication.

## What went wrong (and what it taught)

A few things broke during development that were worth learning from — not
just fixing.

### The histogram that wasn't a histogram

Early on, the "price distribution" chart plotted one bar per product
instead of grouping prices into ranges — with 100+ products, it rendered
as unreadable noise. The fix required actually binning the data with
`pd.cut()` before handing it to the chart, rather than assuming the
charting library would do it automatically. Chart.js doesn't bin data;
that's the caller's job.

### A single missing `</script>` tag

While wiring up the email subscription popup, the dashboard silently
stopped working — no errors shown, the popup just never appeared. The
cause: a `<script src="...">` tag for an external library was missing its
closing tag, which meant every line of custom JavaScript written
afterward was being swallowed into that same tag and never executed by
the browser. Nothing about this failed loudly; it just did nothing, which
made it harder to find than a normal syntax error.

### Outlier masking in anomaly detection

This was the most interesting bug. The first version of the anomaly
detector computed each category's mean and standard deviation *including*
every product in that category — then compared each product against that
baseline. When testing with a deliberately extreme price (£500 injected
into a category averaging ~£30), the detector failed to flag it.

The reason: the £500 outlier was included in calculating the very average
and standard deviation it was then compared against. It dragged the mean
up and inflated the standard deviation enough that its own z-score no
longer looked extreme — a real statistical phenomenon called outlier
masking. The fix was to exclude each product from its own category's
baseline calculation before scoring it. It's a small code change, but it
only gets caught by actually testing with a known-extreme value rather
than trusting that "the math looks right."

### Duplicate titles breaking the pipeline in production

The pipeline worked perfectly locally, then failed the first time it ran
inside GitHub Actions with `ValueError: cannot reindex on an axis with
duplicate labels`. The scraper had been changed to loop over five
categories individually, and it turned out some books appear in more than
one category on the site — producing two rows with the same title in a
single run. That only became visible once the pipeline ran against the
*real*, larger dataset in a clean environment, rather than the smaller
synthetic sample used during local development. It's a reminder that
"works on my machine" and "works in production" are genuinely different
claims, and CI is what catches the gap.

## What this project demonstrates

- Data collection under real-world constraints (scraping, scheduling, rate limiting)
- Persistent data history rather than one-off snapshots
- Statistically sound analysis, including catching and fixing a subtle
  methodological error rather than shipping a model that "ran without
  crashing"
- Full automation with verified CI (not just a script that could be
  automated in theory)
- Communicating findings to two different audiences in two different formats
- Debugging across the full stack — Python, JavaScript, CSS, CI
  configuration, and statistics

## What I'd do differently with more time

- Move from CSV storage to SQLite as history grows, for easier querying
- Add automatic email delivery of the PDF to dashboard subscribers
  (currently the signup is captured; the send step is a natural next
  addition)
- Track more categories and a longer history window before leaning harder
  on the forecasting model, since its confidence is explicitly tied to how
  much data exists
