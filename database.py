from __future__ import annotations
import os
import json
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path

DB_FILE = Path(__file__).parent / "data" / "db.json"

DEFAULTS = {
    "users": {},
    "shops": {},
    "my_products": {},
    "competitor_prices": {},
    "price_history": [],
    "alerts": {},
    "employees": {},
    "activity_log": [],
    "price_requests": [],
    "supplier_prices": {},
    "stock": {},
    "daily_sales": {},
    "transactions": {},
    "loyalty": {},
    "feedback": {},
}


def _ensure_db():
    DB_FILE.parent.mkdir(exist_ok=True)
    if not DB_FILE.exists():
        DB_FILE.write_text(json.dumps(DEFAULTS, indent=2))


def _load():
    _ensure_db()
    db = json.loads(DB_FILE.read_text())
    for k, v in DEFAULTS.items():
        db.setdefault(k, type(v)())
    return db


def _save(data):
    _ensure_db()
    DB_FILE.write_text(json.dumps(data, indent=2, default=str))


# --- Users ---

def create_user(username: str, password_hash: str, shop_name: str):
    db = _load()
    if username in db["users"]:
        return False
    store_id = "store_1"
    db["users"][username] = {
        "password_hash": password_hash,
        "shop_name": shop_name,
        "role": "owner",
        "owner": username,
        "created_at": datetime.utcnow().isoformat(),
        "settings": {"low_margin_threshold": 10, "target_margin": 25},
        "stores": [{"id": store_id, "name": shop_name, "created_at": datetime.utcnow().isoformat()}],
        "active_store": store_id,
    }
    db["shops"][username] = {"name": shop_name}
    _save(db)
    return True


def get_user(username: str):
    db = _load()
    return db["users"].get(username)


def get_owner(username: str) -> str:
    user = get_user(username)
    if not user:
        return username
    return user.get("owner", username)


def is_owner(username: str) -> bool:
    user = get_user(username)
    return user.get("role", "owner") == "owner" if user else False


# --- Multi-Store ---

def get_stores(username: str) -> list[dict]:
    owner = get_owner(username)
    user = get_user(owner)
    if not user:
        return []
    stores = user.get("stores", [])
    if not stores:
        stores = [{"id": "store_1", "name": user.get("shop_name", "My Shop"), "created_at": ""}]
        db = _load()
        db["users"][owner]["stores"] = stores
        db["users"][owner]["active_store"] = "store_1"
        _save(db)
    return stores


def get_active_store(username: str) -> str:
    owner = get_owner(username)
    user = get_user(owner)
    if not user:
        return "store_1"
    stores = user.get("stores", [])
    active = user.get("active_store", "")
    if not active or not any(s["id"] == active for s in stores):
        return stores[0]["id"] if stores else "store_1"
    return active


def get_active_store_name(username: str) -> str:
    owner = get_owner(username)
    user = get_user(owner)
    if not user:
        return "My Shop"
    active = get_active_store(username)
    for s in user.get("stores", []):
        if s["id"] == active:
            return s["name"]
    return user.get("shop_name", "My Shop")


def set_active_store(username: str, store_id: str):
    owner = get_owner(username)
    db = _load()
    user = db["users"].get(owner)
    if user and any(s["id"] == store_id for s in user.get("stores", [])):
        user["active_store"] = store_id
        _save(db)
        return True
    return False


def add_store(username: str, store_name: str) -> str | None:
    owner = get_owner(username)
    db = _load()
    user = db["users"].get(owner)
    if not user:
        return None
    stores = user.setdefault("stores", [])
    store_id = f"store_{len(stores) + 1}"
    stores.append({"id": store_id, "name": store_name, "created_at": datetime.utcnow().isoformat()})
    user["active_store"] = store_id
    log_activity(db, owner, owner, "store_added", f"Added store: {store_name}")
    _save(db)
    return store_id


def remove_store(username: str, store_id: str) -> bool:
    owner = get_owner(username)
    db = _load()
    user = db["users"].get(owner)
    if not user:
        return False
    stores = user.get("stores", [])
    if len(stores) <= 1:
        return False
    user["stores"] = [s for s in stores if s["id"] != store_id]
    if user.get("active_store") == store_id:
        user["active_store"] = user["stores"][0]["id"]
    log_activity(db, owner, owner, "store_removed", f"Removed store: {store_id}")
    _save(db)
    return True


def _store_key(username: str) -> str:
    owner = get_owner(username)
    store_id = get_active_store(username)
    return f"{owner}:{store_id}"


# --- Employees ---

def create_employee(owner: str, emp_username: str, password_hash: str, role: str = "viewer"):
    db = _load()
    if emp_username in db["users"]:
        return False
    owner_data = db["users"].get(owner, {})
    db["users"][emp_username] = {
        "password_hash": password_hash,
        "shop_name": owner_data.get("shop_name", ""),
        "role": role,
        "owner": owner,
        "created_at": datetime.utcnow().isoformat(),
    }
    emps = db["employees"].setdefault(owner, [])
    emps.append({"username": emp_username, "role": role, "created_at": datetime.utcnow().isoformat()})
    log_activity(db, owner, emp_username, "employee_created", f"Created employee {emp_username} with role {role}")
    _save(db)
    return True


def get_employees(owner: str) -> list[dict]:
    db = _load()
    return db.get("employees", {}).get(owner, [])


def remove_employee(owner: str, emp_username: str):
    db = _load()
    emps = db.get("employees", {}).get(owner, [])
    db["employees"][owner] = [e for e in emps if e["username"] != emp_username]
    db["users"].pop(emp_username, None)
    log_activity(db, owner, owner, "employee_removed", f"Removed employee {emp_username}")
    _save(db)


# --- Activity Log ---

def log_activity(db_or_none, owner: str, actor: str, action: str, detail: str = ""):
    if db_or_none is None:
        db = _load()
        save = True
    else:
        db = db_or_none
        save = False
    logs = db.setdefault("activity_log", [])
    logs.append({
        "owner": owner,
        "actor": actor,
        "action": action,
        "detail": detail,
        "timestamp": datetime.utcnow().isoformat(),
    })
    if len(logs) > 500:
        db["activity_log"] = logs[-500:]
    if save:
        _save(db)


def get_activity_log(owner: str, limit: int = 50) -> list[dict]:
    db = _load()
    logs = [l for l in db.get("activity_log", []) if l.get("owner") == owner]
    return logs[-limit:]


# --- Price Change Requests ---

def create_price_request(owner: str, requester: str, product_name: str, new_price: float, reason: str = ""):
    db = _load()
    reqs = db.setdefault("price_requests", [])
    reqs.append({
        "id": len(reqs) + 1,
        "owner": owner,
        "requester": requester,
        "product_name": product_name,
        "new_price": new_price,
        "reason": reason,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    })
    log_activity(db, owner, requester, "price_request", f"Requested {product_name} -> £{new_price:.2f}")
    _save(db)


def get_price_requests(owner: str) -> list[dict]:
    db = _load()
    return [r for r in db.get("price_requests", []) if r.get("owner") == owner and r.get("status") == "pending"]


def resolve_price_request(owner: str, req_id: int, approved: bool):
    db = _load()
    for r in db.get("price_requests", []):
        if r.get("id") == req_id and r.get("owner") == owner:
            r["status"] = "approved" if approved else "rejected"
            r["resolved_at"] = datetime.utcnow().isoformat()
            if approved:
                products = db.get("my_products", {}).get(owner, [])
                for p in products:
                    if p["name"] == r["product_name"]:
                        p["price"] = r["new_price"]
                        break
            log_activity(db, owner, owner, "price_request_resolved",
                         f"{'Approved' if approved else 'Rejected'} {r['product_name']} -> £{r['new_price']:.2f}")
            break
    _save(db)


# --- Products ---

def set_my_products(username: str, products: list[dict]):
    key = _store_key(username)
    db = _load()
    db["my_products"][key] = products
    _save(db)


def get_my_products(username: str) -> list[dict]:
    key = _store_key(username)
    db = _load()
    products = db["my_products"].get(key, [])
    if not products:
        owner = get_owner(username)
        products = db["my_products"].get(owner, [])
    return products


# --- Competitor Prices ---

def save_competitor_prices(username: str, product_name: str, prices: list[dict]):
    owner = get_owner(username)
    store_key = _store_key(username)
    db = _load()
    key = f"{store_key}:{product_name}"

    old_prices = {}
    old_data = db["competitor_prices"].get(key, {})
    for p in old_data.get("prices", []):
        old_prices[p["store"]] = p["price"]

    alerts = db.setdefault("alerts", {}).setdefault(owner, [])
    for p in prices:
        old_price = old_prices.get(p["store"])
        if old_price is not None and p["price"] < old_price:
            alerts.append({
                "product": product_name,
                "store": p["store"],
                "old_price": old_price,
                "new_price": p["price"],
                "drop": round(old_price - p["price"], 2),
                "timestamp": datetime.utcnow().isoformat(),
            })
    if len(alerts) > 50:
        db["alerts"][owner] = alerts[-50:]

    db["competitor_prices"][key] = {
        "prices": prices,
        "updated_at": datetime.utcnow().isoformat(),
    }
    db.setdefault("price_history", []).append({
        "username": owner,
        "product_name": product_name,
        "prices": prices,
        "timestamp": datetime.utcnow().isoformat(),
    })
    log_activity(db, owner, username, "scan", f"Scanned {product_name}: {len(prices)} stores")
    _save(db)


def get_alerts(username: str) -> list[dict]:
    owner = get_owner(username)
    db = _load()
    return db.get("alerts", {}).get(owner, [])


def clear_alerts(username: str):
    owner = get_owner(username)
    db = _load()
    db.setdefault("alerts", {})[owner] = []
    _save(db)


def get_all_competitor_prices(username: str) -> dict:
    store_key = _store_key(username)
    owner = get_owner(username)
    db = _load()
    result = {}
    prefix = f"{store_key}:"
    for key, value in db["competitor_prices"].items():
        if key.startswith(prefix):
            product_name = key[len(prefix):]
            result[product_name] = value
    if not result:
        prefix2 = f"{owner}:"
        for key, value in db["competitor_prices"].items():
            if key.startswith(prefix2):
                parts = key[len(prefix2):]
                if ":" not in parts:
                    result[parts] = value
    return result


def get_price_history(username: str, product_name: str, days: int = 30) -> list[dict]:
    owner = get_owner(username)
    db = _load()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    return [
        entry for entry in db.get("price_history", [])
        if entry["username"] == owner
        and entry["product_name"] == product_name
        and entry["timestamp"] >= cutoff
    ]


# --- Supplier Prices ---

def set_supplier_price(username: str, product_name: str, supplier: str, price: float):
    owner = get_owner(username)
    store_key = _store_key(username)
    db = _load()
    sp = db.setdefault("supplier_prices", {}).setdefault(store_key, {})
    history = sp.setdefault(product_name, [])
    history.append({"supplier": supplier, "price": price, "date": datetime.utcnow().isoformat()})
    if len(history) > 100:
        sp[product_name] = history[-100:]
    log_activity(db, owner, username, "supplier_price", f"{product_name} from {supplier}: £{price:.2f}")
    _save(db)


def get_supplier_prices(username: str) -> dict:
    store_key = _store_key(username)
    db = _load()
    result = db.get("supplier_prices", {}).get(store_key, {})
    if not result:
        owner = get_owner(username)
        result = db.get("supplier_prices", {}).get(owner, {})
    return result


# --- Stock ---

def update_stock(username: str, product_name: str, status: str):
    owner = get_owner(username)
    store_key = _store_key(username)
    db = _load()
    stk = db.setdefault("stock", {}).setdefault(store_key, {})
    stk[product_name] = {"status": status, "updated_at": datetime.utcnow().isoformat()}
    log_activity(db, owner, username, "stock_update", f"{product_name}: {status}")
    _save(db)


def get_stock(username: str) -> dict:
    store_key = _store_key(username)
    db = _load()
    result = db.get("stock", {}).get(store_key, {})
    if not result:
        owner = get_owner(username)
        result = db.get("stock", {}).get(owner, {})
    return result


# --- Daily Sales ---

def set_daily_sales(username: str, product_name: str, units: int):
    store_key = _store_key(username)
    db = _load()
    sales = db.setdefault("daily_sales", {}).setdefault(store_key, {})
    sales[product_name] = {"units": units, "updated_at": datetime.utcnow().isoformat()}
    _save(db)


def get_daily_sales(username: str) -> dict:
    store_key = _store_key(username)
    db = _load()
    result = db.get("daily_sales", {}).get(store_key, {})
    if not result:
        owner = get_owner(username)
        result = db.get("daily_sales", {}).get(owner, {})
    return result


# --- Smart Pricing ---

def get_smart_recommendation(my_price: float, cost_price: float | None, competitors: list[dict],
                              target_margin: float = 25) -> dict:
    if not competitors:
        return {"recommended": None, "reason": "No competitor data", "elasticity": "unknown",
                "avg_competitor": 0, "cheapest_competitor": 0, "price_spread": 0}

    prices = [c["price"] for c in competitors]
    avg = sum(prices) / len(prices)
    cheapest = min(prices)
    most_exp = max(prices)

    if cost_price and cost_price > 0:
        min_price = round(cost_price * (1 + target_margin / 100), 2)
    else:
        min_price = round(avg * 0.85, 2)

    if my_price < cheapest * 0.85:
        recommended = round(cheapest * 0.95, 2)
        reason = "You're significantly cheaper than all competitors — you could raise this price"
        elasticity = "high_opportunity"
    elif my_price > most_exp:
        recommended = round(avg * 0.97, 2)
        reason = "You're the most expensive — consider matching the average"
        elasticity = "overpriced"
    else:
        recommended = round(avg * 0.97, 2)
        reason = "Priced competitively"
        elasticity = "competitive"

    recommended = max(recommended, min_price)

    return {
        "recommended": recommended,
        "reason": reason,
        "elasticity": elasticity,
        "avg_competitor": round(avg, 2),
        "cheapest_competitor": round(cheapest, 2),
        "price_spread": round(most_exp - cheapest, 2),
    }


# --- Basket Comparison ---

def get_basket_comparison(username: str) -> dict:
    all_prices = get_all_competitor_prices(username)
    my_products = get_my_products(username)

    store_totals = {}
    my_total = 0

    for product in my_products:
        name = product["name"]
        my_total += product["price"]
        comp_data = all_prices.get(name, {})
        for cp in comp_data.get("prices", []):
            store_totals.setdefault(cp["store"], {"total": 0, "count": 0})
            store_totals[cp["store"]]["total"] += cp["price"]
            store_totals[cp["store"]]["count"] += 1

    result = []
    for store, data in sorted(store_totals.items(), key=lambda x: x[1]["total"]):
        savings = round(data["total"] - my_total, 2)
        result.append({
            "store": store,
            "total": round(data["total"], 2),
            "count": data["count"],
            "vs_you": savings,
        })

    return {"my_total": round(my_total, 2), "stores": result}


# --- Price Velocity ---

def get_price_velocity(username: str) -> list[dict]:
    owner = get_owner(username)
    db = _load()
    history = [h for h in db.get("price_history", []) if h["username"] == owner]

    store_changes = {}
    store_last = {}
    for entry in history:
        for p in entry["prices"]:
            key = f"{p['store']}:{entry['product_name']}"
            last = store_last.get(key)
            if last is not None and abs(last - p["price"]) > 0.001:
                store_changes.setdefault(p["store"], {"changes": 0, "total_shift": 0})
                store_changes[p["store"]]["changes"] += 1
                store_changes[p["store"]]["total_shift"] += abs(p["price"] - last)
            store_last[key] = p["price"]

    result = []
    for store, data in sorted(store_changes.items(), key=lambda x: -x[1]["changes"]):
        result.append({
            "store": store,
            "changes": data["changes"],
            "avg_shift": round(data["total_shift"] / max(data["changes"], 1), 2),
        })
    return result


# --- Dashboard Data ---

def get_dashboard_data(username: str) -> dict:
    owner = get_owner(username)
    my_products = get_my_products(username)
    all_prices = get_all_competitor_prices(username)
    user_data = get_user(owner) or {}
    settings = user_data.get("settings", {"low_margin_threshold": 10, "target_margin": 25})
    stock_data = get_stock(username)
    sales_data = get_daily_sales(username)

    comparisons = []
    total_revenue = 0
    total_cost = 0
    low_margin_alerts = []
    daily_profit = 0

    for product in my_products:
        name = product["name"]
        my_price = product["price"]
        cost_price = product.get("cost_price")
        competitor_data = all_prices.get(name, {})
        competitor_prices = competitor_data.get("prices", [])

        cheapest = None
        most_expensive = None
        for cp in competitor_prices:
            if cheapest is None or cp["price"] < cheapest["price"]:
                cheapest = cp
            if most_expensive is None or cp["price"] > most_expensive["price"]:
                most_expensive = cp

        status = "no_data"
        if cheapest:
            if my_price < cheapest["price"]:
                status = "cheapest"
            elif my_price > most_expensive["price"]:
                status = "most_expensive"
            else:
                status = "mid_range"

        margin = round(my_price - cost_price, 2) if cost_price else None
        margin_pct = round((margin / my_price) * 100, 1) if margin and my_price > 0 else None

        smart = get_smart_recommendation(my_price, cost_price, competitor_prices, settings.get("target_margin", 25))

        stock_info = stock_data.get(name, {})
        units_per_day = sales_data.get(name, {}).get("units", 0)
        product_daily_profit = round(margin * units_per_day, 2) if margin and units_per_day else 0
        daily_profit += product_daily_profit

        if margin_pct is not None and margin_pct < settings.get("low_margin_threshold", 10):
            low_margin_alerts.append({"name": name, "margin_pct": margin_pct})

        if cost_price:
            total_revenue += my_price
            total_cost += cost_price

        comparisons.append({
            "name": name,
            "my_price": my_price,
            "cost_price": cost_price,
            "size": product.get("size", ""),
            "brand": product.get("brand", ""),
            "category": product.get("category", "Other"),
            "margin": margin,
            "margin_pct": margin_pct,
            "avg_competitor": smart["avg_competitor"],
            "recommended_price": smart["recommended"],
            "recommendation_reason": smart["reason"],
            "elasticity": smart["elasticity"],
            "price_spread": smart.get("price_spread"),
            "competitors": competitor_prices,
            "cheapest": cheapest,
            "most_expensive": most_expensive,
            "status": status,
            "last_updated": competitor_data.get("updated_at", "Never"),
            "stock_status": stock_info.get("status", "in_stock"),
            "units_per_day": units_per_day,
            "daily_profit": product_daily_profit,
        })

    avg_margin = round(((total_revenue - total_cost) / total_revenue) * 100, 1) if total_revenue > 0 else 0
    total_margin = round(total_revenue - total_cost, 2)

    categories = {}
    for c in comparisons:
        cat = c["category"]
        categories.setdefault(cat, []).append(c)

    alerts = get_alerts(username)
    price_requests = get_price_requests(owner)

    return {
        "shop_name": get_active_store_name(username),
        "comparisons": comparisons,
        "categories": categories,
        "total_products": len(my_products),
        "cheaper_count": sum(1 for c in comparisons if c["status"] == "cheapest"),
        "expensive_count": sum(1 for c in comparisons if c["status"] == "most_expensive"),
        "last_scan": max((c["last_updated"] for c in comparisons if c["last_updated"] != "Never"), default="Never"),
        "avg_margin_pct": avg_margin,
        "total_margin": total_margin,
        "total_revenue": round(total_revenue, 2),
        "daily_profit": round(daily_profit, 2),
        "weekly_profit": round(daily_profit * 7, 2),
        "monthly_profit": round(daily_profit * 30, 2),
        "alerts": alerts[-10:],
        "low_margin_alerts": low_margin_alerts,
        "price_requests": price_requests,
        "settings": settings,
    }


# --- Heatmap Data ---

def get_heatmap_data(username: str) -> dict:
    all_prices = get_all_competitor_prices(username)
    my_products = get_my_products(username)
    stores = set()
    products = []

    for product in my_products:
        name = product["name"]
        comp_data = all_prices.get(name, {})
        store_prices = {}
        for cp in comp_data.get("prices", []):
            stores.add(cp["store"])
            store_prices[cp["store"]] = cp["price"]
        products.append({"name": name, "my_price": product["price"], "store_prices": store_prices})

    stores = sorted(stores)
    return {"stores": stores, "products": products}


# --- Reorder Suggestions ---

def get_reorder_suggestions(username: str) -> list[dict]:
    stock = get_stock(username)
    my_products = get_my_products(username)
    all_prices = get_all_competitor_prices(username)
    suggestions = []

    for product in my_products:
        name = product["name"]
        stock_status = stock.get(name, {}).get("status", "in_stock")
        if stock_status in ("low", "out_of_stock"):
            margin = (product["price"] - product.get("cost_price", 0)) if product.get("cost_price") else 0
            comp_data = all_prices.get(name, {})
            comp_count = len(comp_data.get("prices", []))
            priority = "high" if stock_status == "out_of_stock" else "medium"
            if margin > 0.5 and comp_count > 3:
                priority = "high"
            suggestions.append({
                "name": name,
                "stock_status": stock_status,
                "margin": round(margin, 2),
                "priority": priority,
                "category": product.get("category", "Other"),
            })

    suggestions.sort(key=lambda x: 0 if x["priority"] == "high" else 1)
    return suggestions


# --- CSV Export ---

def export_csv(username: str) -> str:
    my_products = get_my_products(username)
    all_prices = get_all_competitor_prices(username)
    lines = ["Product,Size,Category,Your Price,Cost Price,Margin,Avg Competitor,Status"]

    for product in my_products:
        name = product["name"]
        comp_data = all_prices.get(name, {})
        comp_prices = comp_data.get("prices", [])
        avg_comp = round(sum(c["price"] for c in comp_prices) / len(comp_prices), 2) if comp_prices else ""
        margin = round(product["price"] - product.get("cost_price", 0), 2) if product.get("cost_price") else ""

        cheapest = min((c["price"] for c in comp_prices), default=None)
        most_exp = max((c["price"] for c in comp_prices), default=None)
        if cheapest is None:
            status = "no_data"
        elif product["price"] < cheapest:
            status = "cheapest"
        elif product["price"] > most_exp:
            status = "most_expensive"
        else:
            status = "mid_range"

        lines.append(f'"{name}","{product.get("size","")}","{product.get("category","Other")}",{product["price"]},{product.get("cost_price","")},{margin},{avg_comp},{status}')

    return "\n".join(lines)


# --- 1. Price Sensitivity Segmentation ---

def record_transaction(username: str, customer_phone: str, items: list[dict], total: float):
    store_key = _store_key(username)
    owner = get_owner(username)
    db = _load()
    txns = db.setdefault("transactions", {}).setdefault(store_key, [])
    txns.append({
        "customer": customer_phone,
        "items": items,
        "total": total,
        "timestamp": datetime.utcnow().isoformat(),
        "recorded_by": username,
    })
    if len(txns) > 5000:
        db["transactions"][store_key] = txns[-5000:]
    _save(db)


def get_transactions(username: str) -> list[dict]:
    store_key = _store_key(username)
    db = _load()
    return db.get("transactions", {}).get(store_key, [])


def get_customer_segmentation(username: str) -> dict:
    products = get_my_products(username)
    all_prices = get_all_competitor_prices(username)
    sales = get_daily_sales(username)
    txns = get_transactions(username)

    product_map = {p["name"]: p for p in products}
    segments = {"price_conscious": 0, "quality_seeking": 0, "convenience_driven": 0}
    product_segments = []

    for product in products:
        name = product["name"]
        comp = all_prices.get(name, {}).get("prices", [])
        if not comp:
            continue
        avg_comp = sum(c["price"] for c in comp) / len(comp)
        cheapest_comp = min(c["price"] for c in comp)
        my_price = product["price"]
        units = sales.get(name, {}).get("units", 0)

        if my_price <= cheapest_comp and units > 0:
            segments["price_conscious"] += units
            seg = "price_conscious"
        elif my_price > avg_comp * 1.1 and units > 0:
            segments["quality_seeking"] += units
            seg = "quality_seeking"
        elif units > 0:
            segments["convenience_driven"] += units
            seg = "convenience_driven"
        else:
            seg = "unknown"

        product_segments.append({"name": name, "segment": seg, "units": units, "price_vs_avg": round(my_price - avg_comp, 2)})

    total_units = sum(segments.values()) or 1
    dominant = max(segments, key=segments.get) if any(segments.values()) else "unknown"

    customer_profiles = {}
    for txn in txns:
        phone = txn.get("customer", "walk-in")
        if phone not in customer_profiles:
            customer_profiles[phone] = {"visits": 0, "total_spend": 0, "avg_basket": 0, "items_bought": []}
        customer_profiles[phone]["visits"] += 1
        customer_profiles[phone]["total_spend"] += txn["total"]
        customer_profiles[phone]["items_bought"].extend([i["name"] for i in txn.get("items", [])])
    for phone, prof in customer_profiles.items():
        prof["avg_basket"] = round(prof["total_spend"] / max(prof["visits"], 1), 2)

    return {
        "segments": {k: {"count": v, "pct": round(v / total_units * 100, 1)} for k, v in segments.items()},
        "dominant_segment": dominant,
        "product_segments": product_segments,
        "customer_profiles": list(customer_profiles.items())[:20],
    }


# --- 2. Loss Leader Strategy Engine ---

def get_loss_leader_analysis(username: str) -> list[dict]:
    products = get_my_products(username)
    all_prices = get_all_competitor_prices(username)
    sales = get_daily_sales(username)
    results = []

    for product in products:
        name = product["name"]
        cost = product.get("cost_price")
        if not cost:
            continue
        comp = all_prices.get(name, {}).get("prices", [])
        if not comp:
            continue
        cheapest_comp = min(c["price"] for c in comp)
        units = sales.get(name, {}).get("units", 0)
        margin = product["price"] - cost
        category = product.get("category", "Other")
        is_staple = category in ("Dairy", "Bread & Bakery")
        loss_leader_price = round(cost * 0.95, 2)
        footfall_score = 0
        if is_staple:
            footfall_score += 3
        if units > 10:
            footfall_score += 2
        elif units > 5:
            footfall_score += 1
        if cheapest_comp > cost:
            footfall_score += 2
        results.append({
            "name": name, "category": category, "cost": cost,
            "current_price": product["price"], "margin": round(margin, 2),
            "cheapest_competitor": round(cheapest_comp, 2),
            "loss_leader_price": loss_leader_price,
            "savings_vs_competitor": round(cheapest_comp - loss_leader_price, 2),
            "units_per_day": units, "footfall_score": footfall_score,
            "is_staple": is_staple,
            "recommendation": "Strong loss leader" if footfall_score >= 5 else "Potential loss leader" if footfall_score >= 3 else "Keep current price",
        })

    results.sort(key=lambda x: -x["footfall_score"])
    return results


# --- 3. Price Anchoring Display ---

def get_anchoring_data(username: str) -> list[dict]:
    products = get_my_products(username)
    all_prices = get_all_competitor_prices(username)
    results = []
    for product in products:
        name = product["name"]
        comp = all_prices.get(name, {}).get("prices", [])
        if not comp:
            continue
        most_exp = max(comp, key=lambda c: c["price"])
        avg_price = sum(c["price"] for c in comp) / len(comp)
        savings = round(most_exp["price"] - product["price"], 2)
        if savings > 0:
            results.append({
                "name": name, "brand": product.get("brand", ""),
                "size": product.get("size", ""),
                "my_price": product["price"],
                "anchor_price": most_exp["price"],
                "anchor_store": most_exp["store"],
                "avg_price": round(avg_price, 2),
                "savings": savings,
                "savings_pct": round((savings / most_exp["price"]) * 100, 1),
            })
    results.sort(key=lambda x: -x["savings_pct"])
    return results


# --- 4. Impulse Buy Placement Suggestions ---

def get_impulse_buy_suggestions(username: str) -> list[dict]:
    products = get_my_products(username)
    sales = get_daily_sales(username)
    results = []
    impulse_categories = {"Snacks", "Confectionery", "Drinks"}

    for product in products:
        name = product["name"]
        cost = product.get("cost_price")
        margin = round(product["price"] - cost, 2) if cost else 0
        margin_pct = round((margin / product["price"]) * 100, 1) if product["price"] > 0 and margin else 0
        units = sales.get(name, {}).get("units", 0)
        category = product.get("category", "Other")
        impulse_score = 0
        if category in impulse_categories:
            impulse_score += 3
        if product["price"] <= 2.00:
            impulse_score += 2
        if margin_pct > 30:
            impulse_score += 2
        if units > 5:
            impulse_score += 1
        placement = "checkout_counter" if impulse_score >= 5 else "end_of_aisle" if impulse_score >= 3 else "shelf"
        results.append({
            "name": name, "category": category, "price": product["price"],
            "margin": margin, "margin_pct": margin_pct,
            "units_per_day": units, "impulse_score": impulse_score,
            "placement": placement,
            "reason": f"{'High margin' if margin_pct > 30 else 'Popular'} {category.lower()} item at £{product['price']:.2f}",
        })
    results.sort(key=lambda x: -x["impulse_score"])
    return results


# --- 5. Dynamic Pricing by Time of Day ---

def get_dynamic_pricing(username: str) -> list[dict]:
    products = get_my_products(username)
    stock = get_stock(username)
    sales = get_daily_sales(username)
    results = []
    perishable_cats = {"Dairy", "Bread & Bakery"}
    now = datetime.utcnow()
    hour = now.hour

    for product in products:
        name = product["name"]
        category = product.get("category", "Other")
        cost = product.get("cost_price")
        stock_status = stock.get(name, {}).get("status", "in_stock")
        units = sales.get(name, {}).get("units", 0)
        is_perishable = category in perishable_cats

        if not is_perishable and stock_status != "low":
            continue

        morning_price = product["price"]
        afternoon_price = product["price"]
        evening_price = product["price"]

        if is_perishable or stock_status == "low":
            evening_price = round(product["price"] * 0.75, 2)
            if cost:
                evening_price = max(evening_price, cost)
            afternoon_price = round(product["price"] * 0.90, 2)
            if cost:
                afternoon_price = max(afternoon_price, cost)

        current_suggested = morning_price
        if hour >= 18:
            current_suggested = evening_price
        elif hour >= 14:
            current_suggested = afternoon_price

        results.append({
            "name": name, "category": category, "is_perishable": is_perishable,
            "current_price": product["price"], "cost_price": cost,
            "stock_status": stock_status,
            "morning_price": morning_price,
            "afternoon_price": afternoon_price,
            "evening_price": evening_price,
            "current_suggested": current_suggested,
            "time_period": "evening" if hour >= 18 else "afternoon" if hour >= 14 else "morning",
        })
    return results


# --- 6. Customer Loyalty Points ---

def add_loyalty_points(username: str, phone: str, points: int, transaction_total: float = 0):
    store_key = _store_key(username)
    owner = get_owner(username)
    db = _load()
    loyalty = db.setdefault("loyalty", {}).setdefault(store_key, {})
    if phone not in loyalty:
        loyalty[phone] = {"points": 0, "total_spend": 0, "visits": 0, "stamps": 0,
                          "joined": datetime.utcnow().isoformat(), "history": []}
    loyalty[phone]["points"] += points
    loyalty[phone]["total_spend"] += transaction_total
    loyalty[phone]["visits"] += 1
    loyalty[phone]["stamps"] = loyalty[phone]["visits"] % 10
    loyalty[phone]["history"].append({
        "points": points, "total": transaction_total,
        "timestamp": datetime.utcnow().isoformat(),
    })
    if len(loyalty[phone]["history"]) > 100:
        loyalty[phone]["history"] = loyalty[phone]["history"][-100:]
    _save(db)
    return loyalty[phone]


def get_loyalty_customer(username: str, phone: str) -> dict | None:
    store_key = _store_key(username)
    db = _load()
    return db.get("loyalty", {}).get(store_key, {}).get(phone)


def get_all_loyalty_customers(username: str) -> dict:
    store_key = _store_key(username)
    db = _load()
    return db.get("loyalty", {}).get(store_key, {})


def redeem_loyalty(username: str, phone: str, points: int) -> bool:
    store_key = _store_key(username)
    db = _load()
    loyalty = db.get("loyalty", {}).get(store_key, {}).get(phone)
    if not loyalty or loyalty["points"] < points:
        return False
    loyalty["points"] -= points
    loyalty["history"].append({
        "points": -points, "total": 0, "redeemed": True,
        "timestamp": datetime.utcnow().isoformat(),
    })
    _save(db)
    return True


# --- 7. Basket Affinity Analysis ---

def get_basket_affinity(username: str) -> list[dict]:
    txns = get_transactions(username)
    if len(txns) < 3:
        products = get_my_products(username)
        sales = get_daily_sales(username)
        affinities = []
        cats = {}
        for p in products:
            cat = p.get("category", "Other")
            cats.setdefault(cat, []).append(p["name"])
        for cat, items in cats.items():
            if len(items) >= 2:
                affinities.append({
                    "item_a": items[0], "item_b": items[1],
                    "confidence": 65, "support": 0,
                    "suggestion": f"Bundle {items[0]} + {items[1]} (same category: {cat})",
                })
        return affinities[:10]

    item_pairs = {}
    item_counts = {}
    for txn in txns:
        items = [i["name"] for i in txn.get("items", [])]
        for item in items:
            item_counts[item] = item_counts.get(item, 0) + 1
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                pair = tuple(sorted([items[i], items[j]]))
                item_pairs[pair] = item_pairs.get(pair, 0) + 1

    affinities = []
    for (a, b), count in sorted(item_pairs.items(), key=lambda x: -x[1]):
        support_a = item_counts.get(a, 1)
        confidence = round((count / support_a) * 100, 1)
        affinities.append({
            "item_a": a, "item_b": b,
            "confidence": confidence, "support": count,
            "suggestion": f"Customers who buy {a} also buy {b} ({confidence}% of the time)",
        })
    return affinities[:10]


# --- 8. Local Price Index ---

def get_local_price_index(username: str) -> dict:
    products = get_my_products(username)
    all_prices = get_all_competitor_prices(username)
    total_my = 0
    total_avg = 0
    matched = 0

    product_indices = []
    for product in products:
        name = product["name"]
        comp = all_prices.get(name, {}).get("prices", [])
        if not comp:
            continue
        avg_comp = sum(c["price"] for c in comp) / len(comp)
        ratio = round((product["price"] / avg_comp) * 100, 1)
        total_my += product["price"]
        total_avg += avg_comp
        matched += 1
        product_indices.append({"name": name, "my_price": product["price"], "avg_area": round(avg_comp, 2), "index": ratio})

    overall_index = round((total_my / total_avg) * 100, 1) if total_avg > 0 else 100
    if overall_index < 90:
        rating = "Very Affordable"
        badge_color = "#27ae60"
    elif overall_index < 97:
        rating = "Affordable"
        badge_color = "#2ecc71"
    elif overall_index < 103:
        rating = "Fair"
        badge_color = "#f39c12"
    elif overall_index < 110:
        rating = "Above Average"
        badge_color = "#e67e22"
    else:
        rating = "Premium"
        badge_color = "#e74c3c"

    return {
        "overall_index": overall_index,
        "rating": rating,
        "badge_color": badge_color,
        "matched_products": matched,
        "total_products": len(products),
        "your_basket": round(total_my, 2),
        "area_basket": round(total_avg, 2),
        "savings": round(total_avg - total_my, 2),
        "product_indices": sorted(product_indices, key=lambda x: x["index"]),
    }


# --- 9. Seasonal Demand Forecasting ---

def get_seasonal_forecast(username: str) -> list[dict]:
    products = get_my_products(username)
    sales = get_daily_sales(username)
    now = datetime.utcnow()
    month = now.month

    seasonal_patterns = {
        "Dairy": {12: 1.3, 1: 1.1, 6: 1.2, 7: 1.2, 8: 1.2, 11: 1.0},
        "Drinks": {6: 1.5, 7: 1.6, 8: 1.5, 12: 1.3, 1: 0.8, 2: 0.8},
        "Confectionery": {2: 1.4, 10: 1.3, 12: 2.0, 11: 1.5, 1: 0.7},
        "Snacks": {6: 1.3, 7: 1.3, 12: 1.5, 1: 0.9},
        "Bread & Bakery": {12: 1.2, 11: 1.1},
        "Frozen": {6: 1.4, 7: 1.5, 8: 1.4, 12: 1.3},
    }

    upcoming_events = []
    if month == 11:
        upcoming_events = ["Christmas prep (Dec)", "New Year (Jan)"]
    elif month == 12:
        upcoming_events = ["Christmas (25 Dec)", "New Year (1 Jan)", "January sales"]
    elif month == 1:
        upcoming_events = ["Dry January", "Back to school"]
    elif month == 2:
        upcoming_events = ["Valentine's Day (14 Feb)"]
    elif month == 3:
        upcoming_events = ["Ramadan (varies)", "Mother's Day"]
    elif month == 5:
        upcoming_events = ["Summer starts", "Bank Holidays"]
    elif month == 6:
        upcoming_events = ["Summer peak", "School holidays"]
    elif month == 9:
        upcoming_events = ["Back to school", "Freshers' week"]
    elif month == 10:
        upcoming_events = ["Halloween (31 Oct)", "Bonfire Night prep"]

    forecasts = []
    for product in products:
        name = product["name"]
        category = product.get("category", "Other")
        units = sales.get(name, {}).get("units", 0)
        pattern = seasonal_patterns.get(category, {})
        multiplier = pattern.get(month, 1.0)
        next_month = (month % 12) + 1
        next_multiplier = pattern.get(next_month, 1.0)
        forecast_units = round(units * next_multiplier)
        action = "Stock up" if next_multiplier > 1.2 else "Reduce stock" if next_multiplier < 0.85 else "Maintain"

        forecasts.append({
            "name": name, "category": category,
            "current_units": units,
            "current_multiplier": multiplier,
            "next_month_multiplier": next_multiplier,
            "forecast_units": forecast_units,
            "action": action,
            "trend": "up" if next_multiplier > 1.1 else "down" if next_multiplier < 0.9 else "stable",
        })
    forecasts.sort(key=lambda x: -x["next_month_multiplier"])
    return {"forecasts": forecasts, "upcoming_events": upcoming_events, "current_month": now.strftime("%B"), "next_month": (now.replace(day=1) + timedelta(days=32)).strftime("%B")}


# --- 10. Customer Feedback ---

def submit_feedback(username: str, rating: int, value_rating: int, range_rating: int, service_rating: int, comment: str = ""):
    store_key = _store_key(username)
    db = _load()
    fb = db.setdefault("feedback", {}).setdefault(store_key, [])
    fb.append({
        "overall": rating, "value": value_rating,
        "range": range_rating, "service": service_rating,
        "comment": comment, "timestamp": datetime.utcnow().isoformat(),
    })
    if len(fb) > 500:
        db["feedback"][store_key] = fb[-500:]
    _save(db)


def get_feedback(username: str) -> dict:
    store_key = _store_key(username)
    db = _load()
    fb_list = db.get("feedback", {}).get(store_key, [])
    if not fb_list:
        return {"count": 0, "avg_overall": 0, "avg_value": 0, "avg_range": 0, "avg_service": 0, "nps": 0, "recent": []}

    n = len(fb_list)
    avg_overall = round(sum(f["overall"] for f in fb_list) / n, 1)
    avg_value = round(sum(f["value"] for f in fb_list) / n, 1)
    avg_range = round(sum(f["range"] for f in fb_list) / n, 1)
    avg_service = round(sum(f["service"] for f in fb_list) / n, 1)
    promoters = sum(1 for f in fb_list if f["overall"] >= 9)
    detractors = sum(1 for f in fb_list if f["overall"] <= 6)
    nps = round(((promoters - detractors) / n) * 100)

    return {
        "count": n, "avg_overall": avg_overall, "avg_value": avg_value,
        "avg_range": avg_range, "avg_service": avg_service,
        "nps": nps, "recent": fb_list[-10:][::-1],
    }
