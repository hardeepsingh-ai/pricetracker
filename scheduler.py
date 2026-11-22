"""Simple daily auto-scan scheduler. Run as: python scheduler.py"""
from __future__ import annotations
import asyncio
import schedule
import time
from database import _load, get_my_products, save_competitor_prices
from scraper import scrape_trolley_prices


async def scan_all_users():
    db = _load()
    for username in db.get("my_products", {}):
        products = get_my_products(username)
        for product in products:
            try:
                prices = await scrape_trolley_prices(product["name"], product.get("size", ""))
                if prices:
                    save_competitor_prices(username, product["name"], prices)
            except Exception:
                continue
    print(f"Auto-scan complete at {time.strftime('%H:%M')}")


def run_scan():
    asyncio.run(scan_all_users())


if __name__ == "__main__":
    schedule.every().day.at("07:00").do(run_scan)
    print("Scheduler running — daily scan at 07:00")
    while True:
        schedule.run_pending()
        time.sleep(60)
