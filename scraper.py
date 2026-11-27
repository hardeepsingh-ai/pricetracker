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
    text = text.lower().replace("-", " ").replace("'", "").replace("&", " and ")
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", text)).strip()


def _tokenise(text: str) -> set[str]:
    stop = {"the", "a", "an", "of", "and", "for", "in", "with", "to", "at"}
    return {w for w in _normalise(text).split() if w and w not in stop}


def _match_score(card_title: str, product_name: str, brand: str, size: str) -> float:
    title_norm = _normalise(card_title)
    title_tokens = _tokenise(card_title)
    product_tokens = _tokenise(product_name)

    if not product_tokens:
        return 0

    matched = set()
    for pt in product_tokens:
        if pt in title_tokens:
            matched.add(pt)
        else:
            for tt in title_tokens:
                if pt in tt or tt in pt:
                    matched.add(pt)
                    break
    word_ratio = len(matched) / len(product_tokens)
    min_ratio = 0.5 if len(product_tokens) <= 2 else 0.6
    if word_ratio < min_ratio:
        return 0

    score = word_ratio * 50

    # Brand match — bonus if present, track penalty for later
    brand_missing = False
    if brand:
        brand_norm = _normalise(brand)
        if brand_norm in title_norm:
            score += 10
        elif brand_norm in _normalise(product_name):
            brand_missing = True

    # Size/quantity is critical — must match the right pack/volume
    if size:
        size_lower = size.lower().strip()
        title_clean = re.sub(r"[^a-z0-9. ]", "", title_norm)

        # Handle multipack sizes like "4 x 380ml" or "6x500ml"
        multi_size = re.match(r"(\d+)\s*x\s*(\d+\.?\d*\s*(?:ml|l|g|kg|cl))", size_lower)
        size_matched = False
        if multi_size:
            pack_count = multi_size.group(1)
            per_unit = re.sub(r"[^a-z0-9]", "", multi_size.group(2))
            title_compact = re.sub(r"[^a-z0-9 ]", "", title_norm)
            if (re.search(r"\b" + re.escape(pack_count) + r"\b", title_compact) and
                per_unit in re.sub(r"[^a-z0-9]", "", title_compact)):
                size_matched = True
            elif per_unit in re.sub(r"[^a-z0-9]", "", title_compact):
                size_matched = True

        # Extract numeric value and unit from size (e.g. "6 pack" -> 6, "500ml" -> 500ml)
        num_match = re.match(r"(\d+\.?\d*)\s*(pack|pk|x|ml|l|g|kg|litre|liter|pint|pt)?s?$", size_lower)

        if not size_matched and num_match:
            num = num_match.group(1)
            unit = (num_match.group(2) or "").rstrip("s")

            if unit in ("pack", "pk", "x", ""):
                # For packs: match if the number appears in title
                # Also match "6x25g" style multipack format
                title_numbers = re.findall(r"\b" + re.escape(num) + r"\b", title_clean)
                if not title_numbers:
                    title_numbers = re.findall(r"\b" + re.escape(num) + r"x\d+", title_clean)
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
    search_norm = _normalise(product_name + " " + size)
    multipack_match = re.search(r"\b(\d+)\s*x\s*\d+", title_norm)
    search_has_multi = re.search(r"\b\d+\s*x\s*\d+", search_norm)
    if multipack_match and not search_has_multi:
        # Don't penalise if search has matching pack count (e.g. "6 pack" matches "6x25g")
        pack_n = multipack_match.group(1)
        search_has_pack = re.search(r"\b" + re.escape(pack_n) + r"\s*(pack|pk)\b", search_norm)
        if not search_has_pack:
            score *= 0.1
    # Also catch pack counts like "8 Coca-Cola" or "12 Pepsi" in title
    # where search is for a single item (no pack/multipack words)
    # Use a moderate penalty so the right product as a multipack still beats
    # a completely wrong single product
    if not search_has_multi and not re.search(r"\b(pack|pk)\b", search_norm):
        pack_match = re.match(r"^\d+\w*\s+(\d+)\s+", title_norm)
        if pack_match:
            pack_num = int(pack_match.group(1))
            if pack_num in (2, 3, 4, 6, 8, 10, 12, 15, 18, 20, 24, 28, 30, 36):
                score *= 0.15

    # Penalise variant/flavour mismatches
    # "strong" variants: always penalise mismatch in either direction
    strong_variants = [
        "zero", "diet", "sugar free", "sugarfree", "max",
        "caffeine free", "decaf", "light",
        "vegan", "meat free", "non dairy", "plant based",
        "alcohol free", "lactose free", "gluten free",
        "mens", "womens", "men", "women", "kids",
        "spreadable",
        "kitchen", "bathroom", "surface",
    ]
    # "flavour" variants: penalise when title has a DIFFERENT flavour
    # Check longest first so "cheese and onion" matches before "cheese"
    flavour_variants = [
        "sour cream and onion", "sour cream and chive",
        "strawberries and cream", "strawberries n cream",
        "salt and vinegar", "cheese and onion",
        "red edition", "white edition", "blue edition",
        "cool original", "chilli heatwave", "tangy cheese",
        "texas bbq", "texas bbq sauce", "bbq",
        "semi skimmed", "slightly salted", "smoky bacon",
        "prawn cocktail", "ready salted", "roast chicken",
        "sweet chilli", "sea salt", "black pepper",
        "pickled onion", "worcester sauce",
        "creamy vanilla", "holiday",
        "fruit and nut", "whole nut", "oreo",
        "pepperoni", "margherita", "ham and pineapple",
        "cream swirl", "caramel nut crunch", "fruit and nut crunch",
        "sugar free",
        "vanilla", "cherry", "lime", "lemon", "strawberry", "mango",
        "chocolate", "caramel", "toffee", "mint", "raspberry",
        "tropical", "orange", "apple", "grape", "blackcurrant",
        "sparkling",
        "salted", "unsalted",
        "smooth", "crunchy",
        "skimmed", "whole",
    ]
    product_lower = _normalise(product_name)

    for v in strong_variants:
        v_re = r"\b" + re.escape(v) + r"\b"
        in_title = bool(re.search(v_re, title_norm))
        in_search = bool(re.search(v_re, product_lower))
        if in_title and not in_search:
            score *= 0.15
            break
        if in_search and not in_title:
            score *= 0.3
            break

    # Build sets of flavours present in title vs search
    # Match longest first, then remove matched text to avoid double-counting
    def _find_flavours(text, variants):
        found = []
        remaining = text
        for v in variants:
            v_re = r"\b" + re.escape(v) + r"\b"
            if re.search(v_re, remaining):
                found.append(v)
                remaining = re.sub(v_re, " ", remaining)
        return set(found)

    search_flavours = _find_flavours(product_lower, flavour_variants)
    title_flavours = _find_flavours(title_norm, flavour_variants)
    # If title has flavours the search doesn't — wrong flavour
    extra_in_title = title_flavours - search_flavours
    # Ignore incidental descriptors that appear in product type descriptions
    incidental = {"salted", "slightly salted", "vanilla", "smooth", "whole",
                  "skimmed", "semi skimmed", "chocolate", "cream"}
    meaningful_extra = extra_in_title - incidental
    if meaningful_extra:
        score *= 0.15
    elif extra_in_title:
        score *= 0.5
    # If search has specific (non-generic) flavours missing from title
    generic_flavours = {"original", "classic"}
    meaningful_missing = (search_flavours - title_flavours) - generic_flavours - incidental
    if meaningful_missing:
        score *= 0.3

    # Penalise titles with many extra tokens not in the search
    generic_title_words = {"bar", "bottle", "can", "pack", "pint", "litre",
                           "sharing", "multipack", "single", "bag", "box",
                           "chocolate", "crisps", "drink", "drinks", "water",
                           "milk", "bread", "roll", "rolls", "cream",
                           "natural", "mineral", "energy", "original", "classic",
                           "slightly", "block", "spread", "spreadable",
                           "sliced", "soft",
                           "free", "range", "large", "small", "extra",
                           "snack", "flavour", "taste", "style", "type",
                           "gentle", "clean", "tissue", "toilet",
                           "liquid", "powder", "gel", "wash", "soap",
                           "anti", "dandruff", "sensitive", "supreme",
                           "moisturising", "nourishing", "conditioning",
                           "mature", "mild", "strong", "finest", "best",
                           "biscuits", "crackers", "cereal", "oats",
                           "fish", "fingers", "chicken", "beef", "pork",
                           "oven", "chips", "frozen", "fresh", "cooked",
                           "omega", "vitamin", "protein", "fibre"}
    extra_tokens = title_tokens - product_tokens - generic_title_words
    # Remove size tokens (numbers, units, combined like 6x25g)
    extra_tokens = {t for t in extra_tokens if not re.match(r"^\d+\.?\d*$", t)
                    and not re.match(r"^\d+x\d+", t)
                    and t not in ("ml", "l", "g", "kg", "cl", "pt", "pints")
                    and not re.match(r"^\d+\w*(?:ml|l|g|kg|cl)$", t)}
    if brand:
        extra_tokens -= _tokenise(brand)
    if len(extra_tokens) >= 3:
        score *= 0.3

    # Apply brand penalty last so it cuts the full score
    if brand_missing:
        score *= 0.15

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
            if (not best_card or best_score < 25) and brand:
                generic_name = product_name
                brand_lower = brand.lower()
                if brand_lower in generic_name.lower():
                    generic_name = re.sub(re.escape(brand_lower), "", generic_name, flags=re.I).strip()
                if not generic_name or len(_tokenise(generic_name)) < 2:
                    generic_name = product_name
                parts2 = [generic_name]
                if size:
                    parts2.append(size)
                query2 = " ".join(parts2)
                search_url2 = f"https://www.trolley.co.uk/search/?q={query2.replace(' ', '+')}"
                # Still check brand so wrong-brand results get penalised
                best_card2, best_score2 = await _find_best_match(client, search_url2, product_name, brand, size)
                if best_score2 > best_score:
                    best_card, best_score = best_card2, best_score2

            if not best_card or best_score < 25:
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

    # Determine a reasonable max price based on size to catch multipack pages
    max_price = 25.0  # generous default
    if size:
        size_lower = size.lower().strip()
        ml_match = re.search(r"(\d+\.?\d*)\s*ml", size_lower)
        l_match = re.search(r"(\d+\.?\d*)\s*l\b", size_lower)
        g_match = re.search(r"(\d+\.?\d*)\s*g\b", size_lower)
        kg_match = re.search(r"(\d+\.?\d*)\s*kg", size_lower)
        pack_match = re.search(r"(\d+)\s*(pack|pk)", size_lower)
        multi_match = re.search(r"(\d+)\s*x", size_lower)
        if ml_match and not multi_match:
            ml = float(ml_match.group(1))
            max_price = max(5.0, ml * 0.02)  # 500ml -> £10 max
        elif l_match and not multi_match:
            litres = float(l_match.group(1))
            max_price = max(5.0, litres * 8.0)  # 2L -> £16 max
        elif g_match and not multi_match:
            grams = float(g_match.group(1))
            max_price = max(5.0, grams * 0.05)  # 200g -> £10 max
        elif kg_match and not multi_match:
            kg = float(kg_match.group(1))
            max_price = max(8.0, kg * 30.0)
        elif pack_match:
            count = int(pack_match.group(1))
            max_price = max(8.0, count * 3.0)  # 6 pack -> £18 max

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

        price_val = float(match.group(1))
        if price_val > max_price:
            continue

        results.append({
            "product_name": product_title[:45],
            "price": price_val,
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
