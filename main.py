from __future__ import annotations
from typing import Optional
from fastapi import FastAPI, Request, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import hashlib
from datetime import datetime
import json
import os

from database import (
    create_user, get_user, get_owner, is_owner,
    set_my_products, get_my_products,
    save_competitor_prices, get_all_competitor_prices,
    get_dashboard_data, get_price_history, get_alerts, clear_alerts,
    create_employee, get_employees, remove_employee,
    get_activity_log, log_activity,
    create_price_request, get_price_requests, resolve_price_request,
    set_supplier_price, get_supplier_prices,
    update_stock, get_stock,
    set_daily_sales, get_daily_sales,
    get_basket_comparison, get_price_velocity, get_heatmap_data,
    get_reorder_suggestions, export_csv,
    get_stores, get_active_store, get_active_store_name, set_active_store, add_store, remove_store,
    record_transaction, get_transactions, get_customer_segmentation,
    get_loss_leader_analysis, get_anchoring_data, get_impulse_buy_suggestions,
    get_dynamic_pricing, add_loyalty_points, get_loyalty_customer,
    get_all_loyalty_customers, redeem_loyalty, get_basket_affinity,
    get_local_price_index, get_seasonal_forecast,
    submit_feedback, get_feedback,
    get_ai_recommendations, get_sentiment_analysis, get_predictive_analytics,
    get_price_elasticity, get_churn_prediction, get_personalised_promotions,
    get_store_layout_heatmap, get_trust_dashboard,
    report_wrong_match,
    track_event, track_session, track_scan, track_price_change,
    track_feature_usage, get_analytics_summary, export_analytics_csv,
)
from scraper import scrape_trolley_prices, search_trolley_products, SAMPLE_PRODUCTS, CATEGORIES
import logging
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="PriceTracker")


@app.get("/health")
async def health():
    import database
    info = {"status": "ok", "use_pg": database._use_pg, "db_url_set": bool(database.DATABASE_URL)}
    try:
        import psycopg2
        info["psycopg2_version"] = psycopg2.__version__
    except Exception as e:
        info["psycopg2_error"] = str(e)
    try:
        db = database._load()
        info["users_count"] = len(db.get("users", {}))
    except Exception as e:
        info["status"] = "error"
        info["error"] = str(e)
    return info
templates = Jinja2Templates(directory="templates")

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

SESSION_COOKIE = "pt_session"


def get_current_user(request: Request) -> str | None:
    username = request.cookies.get(SESSION_COOKIE)
    if username and not get_user(username):
        return None
    return username


def require_login(request: Request) -> str:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_owner(request: Request) -> str:
    user = require_login(request)
    if not is_owner(user):
        raise HTTPException(status_code=403, detail="Owner access required")
    return user


# --- Auth ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return RedirectResponse("/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = get_user(username)
    if not user or user["password_hash"] != hashlib.sha256(password.encode()).hexdigest():
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Invalid username or password"
        })
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(SESSION_COOKIE, username, max_age=86400 * 30)
    track_event(username, "login")
    track_session(username)
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.post("/register")
async def register(request: Request, username: str = Form(...), password: str = Form(...), shop_name: str = Form(...)):
    if len(username) < 3 or len(password) < 4:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Username must be 3+ chars, password 4+ chars"
        })
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if not create_user(username, password_hash, shop_name):
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Username already taken"
        })
    response = RedirectResponse("/setup", status_code=303)
    response.set_cookie(SESSION_COOKIE, username, max_age=86400 * 30)
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


# --- Setup ---

@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not is_owner(user):
        return RedirectResponse("/dashboard", status_code=303)
    products = get_my_products(user)
    return templates.TemplateResponse("setup.html", {
        "request": request, "products": products,
        "sample_products": SAMPLE_PRODUCTS, "categories": CATEGORIES, "username": user,
    })


@app.post("/setup/add")
async def add_product(request: Request, product_name: str = Form(...), my_price: float = Form(...),
                      cost_price: float = Form(None), size: str = Form(""), category: str = Form("Other"),
                      brand: str = Form("")):
    user = get_current_user(request)
    if not user or not is_owner(user):
        return RedirectResponse("/login", status_code=303)
    products = get_my_products(user)
    products.append({
        "name": product_name.strip(), "price": my_price, "cost_price": cost_price,
        "size": size.strip(), "category": category, "brand": brand.strip(),
        "added_at": datetime.utcnow().isoformat(),
    })
    set_my_products(user, products)
    track_event(user, "product_added", {"product": product_name.strip(), "price": my_price, "category": category})
    track_feature_usage(user, "product_search_add" if brand else "manual_add")
    return RedirectResponse("/setup", status_code=303)


@app.post("/setup/remove/{index}")
async def remove_product(request: Request, index: int):
    user = get_current_user(request)
    if not user or not is_owner(user):
        return RedirectResponse("/login", status_code=303)
    products = get_my_products(user)
    if 0 <= index < len(products):
        removed = products.pop(index)
        set_my_products(user, products)
        track_event(user, "product_removed", {"product": removed.get("name", "")})
    return RedirectResponse("/setup", status_code=303)


@app.post("/setup/update/{index}")
async def update_product(request: Request, index: int, my_price: float = Form(...),
                         cost_price: float = Form(None), size: str = Form(""), category: str = Form("Other"),
                         brand: str = Form("")):
    user = get_current_user(request)
    if not user or not is_owner(user):
        return RedirectResponse("/login", status_code=303)
    products = get_my_products(user)
    if 0 <= index < len(products):
        old_price = products[index].get("price", 0)
        products[index]["price"] = my_price
        products[index]["cost_price"] = cost_price
        products[index]["size"] = size.strip()
        products[index]["category"] = category
        products[index]["brand"] = brand.strip()
        if old_price != my_price:
            track_price_change(user, products[index]["name"], old_price, my_price)
            track_event(user, "price_change", {"product": products[index]["name"], "old": old_price, "new": my_price})
    set_my_products(user, products)
    return RedirectResponse("/setup", status_code=303)


# --- Dashboard ---

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    data = get_dashboard_data(user)
    user_info = get_user(user) or {}
    stores = get_stores(user) if is_owner(user) else []
    active = get_active_store(user)
    track_event(user, "page_view", {"page": "dashboard"})
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "data": data, "username": user,
        "is_owner": is_owner(user), "role": user_info.get("role", "owner"),
        "stores": stores, "active_store": active,
    })


# --- Scan ---

@app.post("/api/scan")
async def scan_prices(request: Request):
    user = get_current_user(request)
    if not user:
        return {"error": "not logged in"}
    user_info = get_user(user)
    if user_info and user_info.get("role") == "viewer":
        return {"error": "Viewers cannot scan"}
    products = get_my_products(user)
    scanned = 0
    for product in products:
        try:
            prices = await scrape_trolley_prices(product["name"], product.get("size", ""), product.get("brand", ""))
            if prices:
                save_competitor_prices(user, product["name"], prices)
                scanned += 1
        except Exception:
            continue
    track_event(user, "scan", {"scanned": scanned, "total": len(products)})
    track_scan(user, len(products), scanned)
    track_feature_usage(user, "price_scan")
    return {"success": True, "scanned": scanned, "total": len(products)}


# --- API Endpoints ---

@app.get("/api/price-history/{product_name}")
async def price_history_api(request: Request, product_name: str):
    user = get_current_user(request)
    if not user:
        return {"error": "not logged in"}
    return {"history": get_price_history(user, product_name)}


@app.get("/api/alerts")
async def alerts_api(request: Request):
    user = get_current_user(request)
    if not user:
        return {"error": "not logged in"}
    return {"alerts": get_alerts(user)}


@app.post("/api/alerts/clear")
async def clear_alerts_api(request: Request):
    user = get_current_user(request)
    if not user:
        return {"error": "not logged in"}
    clear_alerts(user)
    return {"success": True}


@app.post("/api/report-wrong-match")
async def report_wrong_match_api(request: Request):
    user = get_current_user(request)
    if not user:
        return {"error": "not logged in"}
    body = await request.json()
    product_name = body.get("product_name", "")
    matched_product = body.get("matched_product", "")
    reason = body.get("reason", "")
    if not product_name:
        return {"error": "missing product_name"}
    report_wrong_match(user, product_name, matched_product, reason)
    return {"success": True, "message": "Report submitted — thank you for helping improve accuracy"}


@app.get("/api/search-products")
async def search_products(request: Request, q: str = ""):
    user = get_current_user(request)
    if not user:
        return {"error": "not logged in"}
    if not q or len(q) < 2:
        return {"results": []}
    results = await search_trolley_products(q.strip())
    track_event(user, "product_search", {"query": q.strip(), "results_count": len(results)})
    track_feature_usage(user, "product_search")
    return {"results": results}


@app.get("/api/basket")
async def basket_api(request: Request):
    user = get_current_user(request)
    if not user:
        return {"error": "not logged in"}
    return get_basket_comparison(user)


@app.get("/api/velocity")
async def velocity_api(request: Request):
    user = get_current_user(request)
    if not user:
        return {"error": "not logged in"}
    return {"velocity": get_price_velocity(user)}


@app.get("/api/heatmap")
async def heatmap_api(request: Request):
    user = get_current_user(request)
    if not user:
        return {"error": "not logged in"}
    return get_heatmap_data(user)


@app.get("/api/export-csv")
async def csv_export(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    csv_data = export_csv(user)
    track_event(user, "export", {"format": "csv"})
    track_feature_usage(user, "csv_export")
    return Response(
        content=csv_data, media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=pricetracker_{datetime.utcnow().strftime('%Y%m%d')}.csv"},
    )


# --- Report ---

@app.get("/report")
async def generate_report(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    data = get_dashboard_data(user)
    return templates.TemplateResponse("report.html", {
        "request": request, "data": data, "username": user,
        "generated_at": datetime.utcnow().strftime("%d %B %Y at %H:%M"),
    })


# --- Employee Management ---

@app.get("/team", response_class=HTMLResponse)
async def team_page(request: Request):
    user = get_current_user(request)
    if not user or not is_owner(user):
        return RedirectResponse("/dashboard", status_code=303)
    employees = get_employees(user)
    logs = get_activity_log(user, limit=30)
    price_reqs = get_price_requests(user)
    return templates.TemplateResponse("team.html", {
        "request": request, "username": user, "employees": employees,
        "activity_log": reversed(logs), "price_requests": price_reqs,
    })


@app.post("/team/add")
async def add_employee(request: Request, emp_username: str = Form(...),
                       emp_password: str = Form(...), emp_role: str = Form("viewer")):
    user = get_current_user(request)
    if not user or not is_owner(user):
        return RedirectResponse("/login", status_code=303)
    password_hash = hashlib.sha256(emp_password.encode()).hexdigest()
    create_employee(user, emp_username.strip(), password_hash, emp_role)
    return RedirectResponse("/team", status_code=303)


@app.post("/team/remove/{emp_username}")
async def remove_emp(request: Request, emp_username: str):
    user = get_current_user(request)
    if not user or not is_owner(user):
        return RedirectResponse("/login", status_code=303)
    remove_employee(user, emp_username)
    return RedirectResponse("/team", status_code=303)


@app.post("/team/request-resolve/{req_id}")
async def resolve_req(request: Request, req_id: int, action: str = Form(...)):
    user = get_current_user(request)
    if not user or not is_owner(user):
        return RedirectResponse("/login", status_code=303)
    resolve_price_request(user, req_id, action == "approve")
    return RedirectResponse("/team", status_code=303)


# --- Employee Price Request ---

@app.post("/api/price-request")
async def submit_price_request(request: Request):
    user = get_current_user(request)
    if not user:
        return {"error": "not logged in"}
    body = await request.json()
    owner = get_owner(user)
    create_price_request(owner, user, body["product_name"], float(body["new_price"]), body.get("reason", ""))
    return {"success": True}


# --- Analytics ---

@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    data = get_dashboard_data(user)
    basket = get_basket_comparison(user)
    velocity = get_price_velocity(user)
    heatmap = get_heatmap_data(user)
    reorder = get_reorder_suggestions(user)
    return templates.TemplateResponse("analytics.html", {
        "request": request, "data": data, "basket": basket,
        "velocity": velocity, "heatmap": heatmap, "reorder": reorder,
        "username": user, "is_owner": is_owner(user),
    })


# --- Stock Management ---

@app.get("/stock", response_class=HTMLResponse)
async def stock_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    products = get_my_products(user)
    stock = get_stock(user)
    sales = get_daily_sales(user)
    supplier = get_supplier_prices(user)
    reorder = get_reorder_suggestions(user)
    return templates.TemplateResponse("stock.html", {
        "request": request, "products": products, "stock": stock,
        "sales": sales, "supplier": supplier, "reorder": reorder,
        "username": user, "is_owner": is_owner(user),
    })


@app.post("/stock/update")
async def update_stock_route(request: Request, product_name: str = Form(...), status: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    update_stock(user, product_name, status)
    return RedirectResponse("/stock", status_code=303)


@app.post("/stock/sales")
async def update_sales(request: Request, product_name: str = Form(...), units: int = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    set_daily_sales(user, product_name, units)
    return RedirectResponse("/stock", status_code=303)


@app.post("/stock/supplier")
async def add_supplier_price(request: Request, product_name: str = Form(...),
                             supplier: str = Form(...), price: float = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    set_supplier_price(user, product_name, supplier, price)
    return RedirectResponse("/stock", status_code=303)


# --- Customer-Facing ---

@app.get("/public/compare/{username}", response_class=HTMLResponse)
async def public_compare(request: Request, username: str):
    data = get_dashboard_data(username)
    return templates.TemplateResponse("public_compare.html", {
        "request": request, "data": data,
    })


@app.get("/display/{username}", response_class=HTMLResponse)
async def display_page(request: Request, username: str):
    data = get_dashboard_data(username)
    products = data.get("comparisons", [])
    store_name = get_active_store_name(username) or username.title() + "'s Store"
    return templates.TemplateResponse("display.html", {
        "request": request, "products": products, "store_name": store_name,
    })


@app.get("/poster", response_class=HTMLResponse)
async def poster_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    data = get_dashboard_data(user)
    return templates.TemplateResponse("poster.html", {
        "request": request, "data": data, "username": user,
    })


# --- Stores ---

@app.get("/stores", response_class=HTMLResponse)
async def stores_page(request: Request):
    user = get_current_user(request)
    if not user or not is_owner(user):
        return RedirectResponse("/dashboard", status_code=303)
    stores = get_stores(user)
    active = get_active_store(user)
    return templates.TemplateResponse("stores.html", {
        "request": request, "username": user, "stores": stores, "active_store": active,
    })


@app.post("/stores/add")
async def add_store_route(request: Request, store_name: str = Form(...)):
    user = get_current_user(request)
    if not user or not is_owner(user):
        return RedirectResponse("/login", status_code=303)
    add_store(user, store_name.strip())
    return RedirectResponse("/stores", status_code=303)


@app.post("/stores/switch/{store_id}")
async def switch_store(request: Request, store_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    set_active_store(user, store_id)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/stores/remove/{store_id}")
async def remove_store_route(request: Request, store_id: str):
    user = get_current_user(request)
    if not user or not is_owner(user):
        return RedirectResponse("/login", status_code=303)
    remove_store(user, store_id)
    return RedirectResponse("/stores", status_code=303)


# --- PWA ---

@app.get("/manifest.json")
async def manifest():
    return {
        "name": "PriceTracker", "short_name": "PriceTracker",
        "start_url": "/dashboard", "display": "standalone",
        "background_color": "#1a1a2e", "theme_color": "#4ecdc4",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }


# --- Consumer Behaviour Features ---

@app.get("/insights", response_class=HTMLResponse)
async def insights_page(request: Request):
    username = get_current_user(request)
    if not username:
        return RedirectResponse("/login", 303)
    segmentation = get_customer_segmentation(username)
    loss_leaders = get_loss_leader_analysis(username)
    anchoring = get_anchoring_data(username)
    impulse = get_impulse_buy_suggestions(username)
    dynamic = get_dynamic_pricing(username)
    affinity = get_basket_affinity(username)
    price_index = get_local_price_index(username)
    seasonal = get_seasonal_forecast(username)
    return templates.TemplateResponse("insights.html", {
        "request": request, "username": username,
        "store_name": get_active_store_name(username),
        "segmentation": segmentation,
        "loss_leaders": loss_leaders[:10],
        "anchoring": anchoring[:10],
        "impulse": impulse[:10],
        "dynamic": dynamic,
        "affinity": affinity,
        "price_index": price_index,
        "seasonal": seasonal,
    })


@app.get("/loyalty", response_class=HTMLResponse)
async def loyalty_page(request: Request):
    username = get_current_user(request)
    if not username:
        return RedirectResponse("/login", 303)
    customers = get_all_loyalty_customers(username)
    return templates.TemplateResponse("loyalty.html", {
        "request": request, "username": username,
        "store_name": get_active_store_name(username),
        "customers": customers,
    })


@app.post("/loyalty/add")
async def loyalty_add(request: Request, phone: str = Form(...), amount: float = Form(0)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse("/login", 303)
    points = int(amount)
    add_loyalty_points(username, phone, points, amount)
    log_activity(None, username, username, "loyalty_add", f"Added {points} loyalty points for {phone}")
    return RedirectResponse("/loyalty", 303)


@app.post("/loyalty/redeem")
async def loyalty_redeem(request: Request, phone: str = Form(...), points: int = Form(...)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse("/login", 303)
    success = redeem_loyalty(username, phone, points)
    if success:
        log_activity(None, username, username, "loyalty_redeem", f"Redeemed {points} points for {phone}")
    return RedirectResponse("/loyalty", 303)


@app.post("/transaction")
async def record_sale(request: Request, customer_phone: str = Form("walk-in"), items_json: str = Form("[]"), total: float = Form(0)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse("/login", 303)
    items = json.loads(items_json)
    record_transaction(username, customer_phone, items, total)
    if customer_phone != "walk-in":
        pts = int(total)
        add_loyalty_points(username, customer_phone, pts, total)
    log_activity(None, username, username, "sale_recorded", f"Sale recorded: £{total:.2f} for {customer_phone}")
    return RedirectResponse("/insights", 303)


@app.get("/feedback", response_class=HTMLResponse)
async def feedback_page(request: Request):
    username = get_current_user(request)
    if not username:
        return RedirectResponse("/login", 303)
    fb = get_feedback(username)
    return templates.TemplateResponse("feedback.html", {
        "request": request, "username": username,
        "store_name": get_active_store_name(username),
        "feedback": fb,
    })


@app.get("/feedback/qr", response_class=HTMLResponse)
async def feedback_qr(request: Request, store: str = ""):
    return templates.TemplateResponse("feedback_form.html", {
        "request": request, "store": store,
    })


@app.post("/feedback/submit")
async def feedback_submit(request: Request, store_owner: str = Form(...), overall: int = Form(...), value: int = Form(3), range_rating: int = Form(3), service: int = Form(3), comment: str = Form("")):
    submit_feedback(store_owner, overall, value, range_rating, service, comment)
    return HTMLResponse("<html><body style='text-align:center;padding:40px;font-family:system-ui'><h2>Thank you!</h2><p>Your feedback has been submitted.</p></body></html>")


@app.get("/anchoring/poster", response_class=HTMLResponse)
async def anchoring_poster(request: Request):
    username = get_current_user(request)
    if not username:
        return RedirectResponse("/login", 303)
    anchoring = get_anchoring_data(username)
    return templates.TemplateResponse("anchoring_poster.html", {
        "request": request, "username": username,
        "store_name": get_active_store_name(username),
        "items": anchoring[:8],
    })


@app.get("/ai-insights", response_class=HTMLResponse)
async def ai_insights_page(request: Request):
    username = get_current_user(request)
    if not username:
        return RedirectResponse("/login", 303)
    recommendations = get_ai_recommendations(username)
    sentiment = get_sentiment_analysis(username)
    predictive = get_predictive_analytics(username)
    elasticity = get_price_elasticity(username)
    churn = get_churn_prediction(username)
    promotions = get_personalised_promotions(username)
    layout = get_store_layout_heatmap(username)
    trust = get_trust_dashboard(username)
    return templates.TemplateResponse("ai_insights.html", {
        "request": request, "username": username,
        "store_name": get_active_store_name(username),
        "recommendations": recommendations,
        "sentiment": sentiment,
        "predictive": predictive,
        "elasticity": elasticity,
        "churn": churn,
        "promotions": promotions,
        "layout": layout,
        "trust": trust,
    })


# --- Analytics Dashboard (GTV Evidence) ---

@app.get("/analytics-usage", response_class=HTMLResponse)
async def analytics_usage_page(request: Request):
    user = get_current_user(request)
    if not user or not is_owner(user):
        return RedirectResponse("/login", status_code=303)
    summary = get_analytics_summary(user)
    track_event(user, "page_view", {"page": "analytics_usage"})
    return templates.TemplateResponse("analytics_usage.html", {
        "request": request, "username": user, "summary": summary,
    })


@app.get("/api/analytics-export")
async def analytics_csv_export(request: Request):
    user = get_current_user(request)
    if not user or not is_owner(user):
        return RedirectResponse("/login", status_code=303)
    csv_data = export_analytics_csv(user)
    track_event(user, "export", {"format": "analytics_csv"})
    return Response(
        content=csv_data, media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=analytics_{datetime.utcnow().strftime('%Y%m%d')}.csv"},
    )


@app.get("/sw.js")
async def service_worker():
    sw = "self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));self.addEventListener('fetch',e=>{e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)))});"
    return Response(content=sw, media_type="application/javascript")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
