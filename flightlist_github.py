# flightlist_scraper.py
# Multi-filter configurable FlightList.io scraper with Telegram alerts

import asyncio
import os
import httpx
import csv
from playwright.async_api import async_playwright

# ========== Load Filters from CSV ==========
FILTERS = []
CSV_FILE = "filters.csv"

def load_filters_from_csv():
    with open(CSV_FILE, newline='', encoding='utf-8-sig') as f:  # <== هنا التغيير
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("enabled", "1").strip() != "1":
                continue
            FILTERS.append({
                "name": row["name"],
                "trip_type": row["trip_type"],
                "origin": row["origin"],
                "depart_from": row["depart_from"],
                "depart_to": row["depart_to"],
                "depart_month": row["depart_month"],
                "depart_year": row["depart_year"],
                "return_from": row.get("return_from"),
                "return_to": row.get("return_to"),
                "return_month": row.get("return_month"),
                "return_year": row.get("return_year"),
                "currency": row["currency"],
                "max_results": row["max_results"],
                "max_budget": row["max_budget"],
            })

# ========== Excluded Countries ==========
EXCLUDED_COUNTRIES = [
    "(PFO)", # Paphos
    "(SKG)", # Thessaloniki
    "(MLA)", # Malta
]

# ========== Telegram Messaging ==========
async def send_telegram_message(message: str):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("[ERROR] Missing Telegram bot token or chat ID.")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

# ========== Scraping Function ==========
async def scrape_flights(page, config):
    print(f"\n[INFO] Running filter: {config['name']}")
    await page.goto("https://www.flightlist.io", wait_until="networkidle")

    await page.locator('#from-input').click()
    await page.keyboard.type(config['origin'], delay=50)
    await page.wait_for_selector(".easy-autocomplete-container .eac-item", timeout=3000)
    await page.locator(".easy-autocomplete-container .eac-item").first.click()

    # Select trip type (One Way or Return)
    trip_type = config.get("trip_type", "One Way")
    await page.select_option("#type", trip_type)

    async def ensure_month_visible(month, year, drp):
        target_text = f"{month} {year}"
        for _ in range(12):
            left_month = await drp.locator(".drp-calendar.left .month").inner_text()
            right_month = await drp.locator(".drp-calendar.right .month").inner_text()
            if left_month.strip() == target_text:
                return 'left'
            if right_month.strip() == target_text:
                return 'right'
            await drp.locator(".drp-calendar.right th.next").click()
            await page.wait_for_timeout(300)
        raise Exception(f"Month {target_text} not found in calendars")

    async def pick_date_range(button_id, from_day, to_day, month, year, title_keyword=None):
        await page.locator(f'#{button_id}').click()
        drp = page.locator(f'.daterangepicker:has-text("{title_keyword}")') if title_keyword else page.locator('.daterangepicker')
        await drp.wait_for(timeout=3000)
        side = await ensure_month_visible(month, year, drp)
        await drp.locator(f".drp-calendar.{side} td.available:not(.off):has-text('{from_day}')").first.click()
        await drp.locator(f".drp-calendar.{side} td.available:not(.off):has-text('{to_day}')").first.click()
        await drp.locator('.applyBtn:enabled').click()

    # Pick departure range
    await pick_date_range("deprange", config['depart_from'], config['depart_to'], config['depart_month'], config['depart_year'], "Departure Date Range")

    if trip_type == "Return":
        await pick_date_range("retrange", config['return_from'], config['return_to'], config['return_month'], config['return_year'], "Return Date Range")

    await page.select_option('#currency', config['currency'])
    await page.locator('button:has-text("Additional Options")').click()
    await page.wait_for_selector('#limit', timeout=2000)
    await page.select_option('#limit', config['max_results'])
    await page.fill('#budget', config['max_budget'])

    await page.locator('#submit').click()
    await page.wait_for_timeout(3000)

    has_flights = await page.locator(".flights-list .flight").count()
    no_results_text = await page.locator("text=No flights found").count()

    if not has_flights and no_results_text:
        print("[INFO] No results found for this filter.")
        return

    flight_cards = page.locator(".flights-list .flight")
    count = await flight_cards.count()
    results = []

    for i in range(count):
        flight = flight_cards.nth(i)
        price = await flight.locator(".price").inner_text()

        # اجمع كل التواريخ والمسارات والأوقات بدل من .nth(0)
        dates = await flight.locator("div.col-md-3 small.text-muted").all_inner_texts()
        routes = await flight.locator(".col-md-5 small.text-muted").all_inner_texts()
        times = await flight.locator(".col-md-3 span.reduced").all_inner_texts()

        route_summary = ""
        for date, time, route in zip(dates, times, routes):
            skip = any(bad_country.lower() in route.lower() for bad_country in EXCLUDED_COUNTRIES)
            if skip:
                print(f"[SKIPPED] Skipped segment due to excluded country in route: {route.strip()}")
                break
            route_summary += f"<b>{date.strip()}</b>\n🕒 {time.strip()}\n✈️ {route.strip()}\n\n"
        else:
            results.append(f"{route_summary}💰 Price: <b>${price}</b>\n---")

    if results:
        header = f"🧭 <b>{config['name']}</b>\n\n"
        await send_telegram_message(header + "\n\n".join(results))
        print(f"[SUCCESS] Sent {len(results)} results to Telegram.")
    else:
        print("[INFO] No results found for this filter after exclusion.")

# ========== Runner ==========
async def run():
    print("[INFO] Launching browser...")
    load_filters_from_csv()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        context = await browser.new_context()
        page = await context.new_page()
        await page.set_viewport_size({"width": 1920, "height": 1080})

        for config in FILTERS:
            try:
                await scrape_flights(page, config)
            except Exception as e:
                print(f"[ERROR] Failed on filter {config['name']}: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
