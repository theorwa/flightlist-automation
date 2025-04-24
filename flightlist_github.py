import asyncio
import os
import httpx
import csv
from datetime import datetime
import re
from playwright.async_api import async_playwright

# ========== Load Filters from CSV ==========
FILTERS = []
CSV_FILE = "filters.csv"

def parse_flexible_date(date_str):
    formats = ["%d-%m-%Y", "%d/%m/%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid date format: {date_str}")

def load_filters_from_csv():
    with open(CSV_FILE, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("enabled", "1").strip() != "1":
                continue
            try:
                # Parse full date parts
                dep_from_date = parse_flexible_date(row["depart_from"])
                dep_to_date = parse_flexible_date(row["depart_to"])
                ret_from_date = parse_flexible_date(row["return_from"]) if row.get("return_from") else None
                ret_to_date = parse_flexible_date(row["return_to"]) if row.get("return_to") else None

                FILTERS.append({
                    "name": row["name"],
                    "trip_type": row["trip_type"],
                    "origin": row["origin"],
                    "destination": row["destination"],
                    "depart_from": str(dep_from_date.day),
                    "depart_to": str(dep_to_date.day),
                    "depart_month_from": dep_from_date.strftime("%b"),
                    "depart_year_from": str(dep_from_date.year),
                    "depart_month_to": dep_to_date.strftime("%b"),
                    "depart_year_to": str(dep_to_date.year),
                    "return_from": str(ret_from_date.day) if ret_from_date else "",
                    "return_to": str(ret_to_date.day) if ret_to_date else "",
                    "return_month_from": ret_from_date.strftime("%b") if ret_from_date else "",
                    "return_year_from": str(ret_from_date.year) if ret_from_date else "",
                    "return_month_to": ret_to_date.strftime("%b") if ret_to_date else "",
                    "return_year_to": str(ret_to_date.year) if ret_to_date else "",
                    "currency": row["currency"],
                    "max_results": row["max_results"],
                    "max_budget": row["max_budget"],
                    "max_days": int(row.get("max_days", 0)) if row.get("max_days") else None
                })
            except Exception as e:
                print(f"[ERROR] Failed to parse row: {row}\nReason: {e}")

# ========== Excluded Countries ==========
EXCLUDED_COUNTRIES = [
    "(PFO)", # Paphos
    "(SKG)", # Thessaloniki
    "(MLA)", # Malta
    "(ATH)", # Athens
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

# ========== Utility Function ==========
def clean_date_string(date_str):
    return re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)

# ========== Scraping Function ==========
async def scrape_flights(page, config):
    print(f"\n[INFO] Running filter: {config['name']}")
    await page.goto("https://www.flightlist.io", wait_until="networkidle")

    if config.get("origin"):
        await page.locator('#from-input').click()
        await page.keyboard.type(config['origin'], delay=50)
        await page.wait_for_selector(".easy-autocomplete-container .eac-item", timeout=3000)
        await page.locator(".easy-autocomplete-container .eac-item").first.click()

    if config.get("destination"):
        await page.locator('#to-input').click()
        await page.keyboard.type(config['destination'], delay=50)
        container = page.locator('#eac-container-to-input .eac-item')
        await container.first.wait_for(state="visible", timeout=3000)
        await container.first.click()

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

    async def pick_date_range(button_id, from_day, to_day, month_from, year_from, month_to, year_to, title_keyword=None):
        await page.locator(f'#{button_id}').click()
        drp = page.locator(f'.daterangepicker:has-text("{title_keyword}")') if title_keyword else page.locator('.daterangepicker')
        await drp.wait_for(timeout=3000)

        side_from = await ensure_month_visible(month_from, year_from, drp)
        await drp.locator(f".drp-calendar.{side_from} td.available:not(.off):has-text('{from_day}')").first.click()

        side_to = await ensure_month_visible(month_to, year_to, drp)
        await drp.locator(f".drp-calendar.{side_to} td.available:not(.off):has-text('{to_day}')").first.click()

        await drp.locator('.applyBtn:enabled').click()

    await pick_date_range(
        "deprange",
        config['depart_from'],
        config['depart_to'],
        config['depart_month_from'],
        config['depart_year_from'],
        config['depart_month_to'],
        config['depart_year_to'],
        "Departure Date Range"
    )

    if trip_type == "Return":
        await pick_date_range(
            "retrange",
            config['return_from'],
            config['return_to'],
            config['return_month_from'],
            config['return_year_from'],
            config['return_month_to'],
            config['return_year_to'],
            "Return Date Range"
        )

    await page.select_option('#currency', config['currency'])
    await page.locator('button:has-text("Additional Options")').click()
    await page.wait_for_selector('#limit', timeout=2000)
    await page.select_option('#limit', config['max_results'])
    await page.fill('#budget', config['max_budget'])

    await page.locator('#submit').click()
    await page.wait_for_timeout(5000)

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
            try:
                date_objects = [datetime.strptime(clean_date_string(d.strip()), "%a %b %d %Y") for d in dates]
                days = (max(date_objects) - min(date_objects)).days + 1
                if config['trip_type'] == "Return" and config.get("max_days") and days > config["max_days"]:
                    print(f"[SKIPPED] Trip duration {days} exceeds max_days={config['max_days']}")
                    continue
                d = f" | {days} أيام"
                sort_date = min(date_objects)
            except:
                d = ""
                sort_date = datetime.max

            trip_icon = "➡️" if config["trip_type"] == "One Way" else "🔁"
            summary_title = f"{trip_icon}{d} | ${price}"

            results.append({"text": f"<b>{summary_title}</b>\n\n{route_summary}\n---", "sort_date": sort_date})

    if results:
        sorted_results = sorted(results, key=lambda r: r["sort_date"])
        header = f"🔎 <b>{config['name']}</b>\n\n"
        await send_telegram_message(header + "\n\n".join([r["text"] for r in sorted_results]))
        print(f"[SUCCESS] Sent {len(sorted_results)} results to Telegram.")
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
