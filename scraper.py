from __future__ import annotations
import httpx
from bs4 import BeautifulSoup
import re
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

CATEGORIES = [
    "Drinks",
    "Dairy",
    "Bread & Bakery",
    "Snacks",
    "Household",
    "Toiletries",
    "Frozen",
    "Confectionery",
    "Other",
]


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _size_matches(title: str, size: str) -> bool:
    if not size:
        return True
    norm_size = _normalise(size)
    norm_title = _normalise(title)
    return norm_size in norm_title


def _brand_matches(title: str, brand: str) -> bool:
    if not brand:
        return True
    norm_brand = _normalise(brand)
    norm_title = _normalise(title)
    return norm_brand in norm_title


async def scrape_trolley_prices(product_name: str, size: str = "", brand: str = "") -> list[dict]:
    """Search Trolley with brand + product + size, pick the best matching result, scrape per-store prices."""
    parts = []
    if brand:
        parts.append(brand)
    parts.append(product_name)
    if size:
        parts.append(size)
    query = " ".join(parts)
    search_url = f"https://www.trolley.co.uk/search/?q={query.replace(' ', '+')}"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(search_url, headers=HEADERS)
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", class_="product-item")
            if not cards:
                return []

            best_card = None
            for card in cards[:10]:
                link = card.find("a")
                if not link:
                    continue
                card_title = link.get_text(" ", strip=True)
                if brand and not _brand_matches(card_title, brand):
                    continue
                if size and not _size_matches(card_title, size):
                    continue
                best_card = card
                break

            if not best_card:
                best_card = cards[0]

            link = best_card.find("a")
            if not link or not link.get("href"):
                return []

            product_url = "https://www.trolley.co.uk" + link["href"]
            product_title = link.get_text(" ", strip=True)
            product_title = re.sub(r"\d+\s*£.*", "", product_title).strip()
            product_title = re.sub(r"^\d+\.?\d*\s*(ml|l|g|kg|pts?|pints?)\s*,?\s*\d*\s*(pts?|pints?)?\s*", "", product_title, flags=re.I).strip()

            detail = await client.get(product_url, headers=HEADERS)
            if detail.status_code != 200:
                return []

    except Exception:
        return []

    detail_soup = BeautifulSoup(detail.text, "html.parser")
    results = []

    for item in detail_soup.find_all("div", class_="_item"):
        svg = item.find("svg", class_="store-logo")
        if not svg:
            continue
        title_el = svg.find("title")
        store = title_el.get_text(strip=True) if title_el else "Unknown"

        if store.lower() in ("ebay", "amazon"):
            continue

        price_el = item.find("div", class_="_price")
        if not price_el:
            continue
        price_text = price_el.get_text(strip=True)
        match = re.match(r"£(\d+\.?\d*)", price_text)
        if not match:
            continue

        results.append({
            "product_name": product_title[:45],
            "price": float(match.group(1)),
            "store": store,
            "scraped_at": datetime.utcnow().isoformat(),
        })

    return results


SAMPLE_PRODUCTS = [
    "semi skimmed milk 2L",
    "semi skimmed milk 1L",
    "whole milk 2L",
    "white bread 800g",
    "wholemeal bread 800g",
    "free range eggs 6 pack",
    "cheddar cheese 400g",
    "butter 250g",
    "coca cola 500ml",
    "pepsi 500ml",
    "lucozade 500ml",
    "lucozade 4 pack",
    "walkers crisps 6 pack",
    "cadbury dairy milk 110g",
    "red bull 250ml",
]
