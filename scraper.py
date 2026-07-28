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
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_FILE = os.path.join(DATA_DIR, "price_history.csv")

# Categories to track. Each is scraped in full (usually 1-3 pages).
CATEGORIES = {
    "Travel": "travel_2",
    "Mystery": "mystery_3",
    "Fiction": "fiction_10",
    "Fantasy": "fantasy_19",
    "Science": "science_22",
}

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (portfolio-price-tracker; educational use)"
}


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_product_card(card, run_timestamp: str, category: str) -> dict:
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
        "category": category,
        "price_gbp": price,
        "in_stock": in_stock,
        "rating": rating,
        "product_url": product_url,
    }

def scrape_all() -> list[dict]:
    run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    records = []

    for category_name, category_slug in CATEGORIES.items():
        page_num = 1
        while True:
            if page_num == 1:
                url = f"{BASE_URL}catalogue/category/books/{category_slug}/index.html"
            else:
                url = f"{BASE_URL}catalogue/category/books/{category_slug}/page-{page_num}.html"

            try:
                soup = fetch_page(url)
            except requests.HTTPError:
                break

            cards = soup.select("article.product_pod")
            if not cards:
                break

            for card in cards:
                records.append(parse_product_card(card, run_timestamp, category_name))

            page_num += 1
            time.sleep(0.5)  # be polite to the server

    return records

def append_to_history(records: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    file_exists = os.path.isfile(HISTORY_FILE)

    fieldnames = [
        "run_timestamp",
        "title",
        "category",
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