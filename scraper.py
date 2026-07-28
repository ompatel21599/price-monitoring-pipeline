"""
scraper.py
Scrapes product listings from books.toscrape.com (a site built for scraping
practice) and appends a snapshot of prices/stock/ratings to a history CSV.

This simulates a real-world competitor price monitoring pipeline:
each run = one "price check" for all tracked products.
"""

import csv
import os
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
CATALOGUE_URL = BASE_URL + "catalogue/page-{}.html"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_FILE = os.path.join(DATA_DIR, "price_history.csv")

# How many category listing pages to scrape. The site has 50 pages of
# ~20 products each. Keep this modest so runs are fast and polite.
MAX_PAGES = 5

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (portfolio-price-tracker; educational use)"
}


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_product_card(card, run_timestamp: str) -> dict:
    title = card.h3.a["title"].strip()

    price_text = card.select_one(".price_color").get_text(strip=True)
    price = float(re.sub(r"[^\d.]", "", price_text))

    availability = card.select_one(".availability").get_text(strip=True)
    in_stock = "In stock" in availability

    rating_classes = card.select_one(".star-rating")["class"]
    rating_word = [c for c in rating_classes if c != "star-rating"][0]
    rating = RATING_WORDS.get(rating_word, None)

    relative_link = card.h3.a["href"]
    product_url = BASE_URL + "catalogue/" + relative_link.replace("../../../", "")

    return {
        "run_timestamp": run_timestamp,
        "title": title,
        "price_gbp": price,
        "in_stock": in_stock,
        "rating": rating,
        "product_url": product_url,
    }


def scrape_all(max_pages: int = MAX_PAGES) -> list[dict]:
    run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    records = []

    for page_num in range(1, max_pages + 1):
        url = CATALOGUE_URL.format(page_num)
        try:
            soup = fetch_page(url)
        except requests.HTTPError:
            # We've run past the last available page
            break

        cards = soup.select("article.product_pod")
        if not cards:
            break

        for card in cards:
            records.append(parse_product_card(card, run_timestamp))

        time.sleep(0.5)  # be polite to the server

    return records


def append_to_history(records: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    file_exists = os.path.isfile(HISTORY_FILE)

    fieldnames = [
        "run_timestamp",
        "title",
        "price_gbp",
        "in_stock",
        "rating",
        "product_url",
    ]

    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(records)


def main():
    print("Starting scrape run...")
    records = scrape_all()
    print(f"Scraped {len(records)} product records.")

    append_to_history(records)
    print(f"Appended to {HISTORY_FILE}")


if __name__ == "__main__":
    main()