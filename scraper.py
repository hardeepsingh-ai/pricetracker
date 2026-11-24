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
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def _tokenise(text: str) -> set[str]:
    stop = {"the", "a", "an", "of", "and", "for", "in", "with", "to", "at"}
    return {w for w in _normalise(text).split() if w and w not in stop}


def _match_score(card_title: str, product_name: str, brand: str, size: str) -> float:
    title_norm = _normalise(card_title)
    title_tokens = _tokenise(card_title)
    product_tokens = _tokenise(product_name)

    if not product_tokens:
        return 0

    matched = product_tokens & title_tokens
    word_ratio = len(matched) / len(product_tokens)
    if word_ratio < 0.5:
        return 0

    score = word_ratio * 50

    # Brand is just a reference — small bonus, no penalty
    if brand and _normalise(brand) in title_norm:
        score += 10

    # Size/quantity is critical — must match the right pack/volume
    if size:
        size_lower = size.lower().strip()
        title_clean = re.sub(r"[^a-z0-9. ]", "", title_norm)

        # Extract numeric value and unit from size (e.g. "6 pack" -> 6, "500ml" -> 500ml)
        num_match = re.match(r"(\d+\.?\d*)\s*(pack|pk|x|ml|l|g|kg|litre|liter|pint|pt)?s?$", size_lower)
        size_matched = False

        if num_match:
            num = num_match.group(1)
            unit = (num_match.group(2) or "").rstrip("s")

            if unit in ("pack", "pk", "x", ""):
                # For packs: match if the number appears in title (e.g. "6" in "6 Free Range Eggs")
                title_numbers = re.findall(r"\b" + re.escape(num) + r"\b", title_clean)
                if title_numbers:
                    size_matched = True
            else:
                # For units: match "500ml", "2l", "250g" etc.
                size_compact = re.sub(r"[^a-z0-9]", "", size_lower)
                if size_compact in re.sub(r"[^a-z0-9]", "", title_clean):
                    size_matched = True
        else:
            # Fallback: direct substring match
            size_compact = re.sub(r"[^a-z0-9]", "", size_lower)
            if size_compact in re.sub(r"[^a-z0-9]", "", title_clean):
                size_matched = True

        if size_matched:
            score += 35
        else:
            score *= 0.3

    # Penalise multipacks when searching for a single item
    multipack_match = re.search(r"\b(\d+)\s*x\s*\d+", title_norm)
    search_has_multi = re.search(r"\b\d+\s*x\s*\d+", _normalise(product_name + " " + size))
    if multipack_match and not search_has_multi:
        score *= 0.1

    # Penalise variant mismatches (zero, diet, vanilla, cherry, etc.)
    variant_words = {"zero", "diet", "sugar free", "sugarfree", "vanilla",
                     "cherry", "lime", "lemon", "strawberry", "mango",
                     "decaf", "light", "max", "caffeine free"}
    product_lower = _normalise(product_name)
    for v in variant_words:
        in_title = v in title_norm
        in_search = v in product_lower
        if in_title and not in_search:
            score *= 0.15
            break

    return score


async def _find_best_match(client, search_url: str, product_name: str, brand: str, size: str):
    """Search Trolley and return (best_card, best_score) or (None, 0)."""
    resp = await client.get(search_url, headers=HEADERS)
    if resp.status_code != 200:
        return None, 0
    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.find_all("div", class_="product-item")
    if not cards:
        return None, 0
    best_card = None
    best_score = 0
    for card in cards[:10]:
        link = card.find("a")
        if not link:
            continue
        card_title = link.get_text(" ", strip=True)
        score = _match_score(card_title, product_name, brand, size)
        if score > best_score:
            best_score = score
            best_card = card
    return best_card, best_score


async def scrape_trolley_prices(product_name: str, size: str = "", brand: str = "") -> list[dict]:
    """Search Trolley, pick the best matching result, scrape per-store prices.
    Tries with brand first, then without brand if no good match found."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            # Try 1: search with brand + product + size
            parts = []
            if brand:
                parts.append(brand)
            parts.append(product_name)
            if size:
                parts.append(size)
            query = " ".join(parts)
            search_url = f"https://www.trolley.co.uk/search/?q={query.replace(' ', '+')}"

            best_card, best_score = await _find_best_match(client, search_url, product_name, brand, size)

            # Try 2: search without brand if no good match
            if (not best_card or best_score < 30) and brand:
                # Strip brand words from product name for a generic search
                generic_name = product_name
                brand_lower = brand.lower()
                if brand_lower in generic_name.lower():
                    generic_name = re.sub(re.escape(brand_lower), "", generic_name, flags=re.I).strip()
                if not generic_name:
                    generic_name = product_name
                parts2 = [generic_name]
                if size:
                    parts2.append(size)
                query2 = " ".join(parts2)
                search_url2 = f"https://www.trolley.co.uk/search/?q={query2.replace(' ', '+')}"
                best_card, best_score = await _find_best_match(client, search_url2, generic_name, "", size)

            if not best_card or best_score < 30:
                return []

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
            "url": product_url,
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
