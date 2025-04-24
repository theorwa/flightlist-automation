# flightlist_scraper.py
# Multi-filter configurable FlightList.io scraper with Telegram alerts

import asyncio
import os
import httpx
from playwright.async_api import async_playwright

# ========== Filters Configuration ==========
FILTERS = [
    {
        "name": "بوخارست 10 - 12 مايو",
        "trip_type": "One Way",
        "origin": "Bucharest",
        "depart_from": "10",
        "depart_to": "12",
        "depart_month": "May",
        "depart_year": "2025",
        "currency": "USD",
        "max_results": "50",
        "max_budget": "30",
    },
    {
        "name": "تل أبيب 29 أبريل - 5 مايو",
        "trip_type": "Return",
        "origin": "Tel Aviv",
        "depart_from": "29",
        "depart_to": "30",
        "depart_month": "Apr",
        "depart_year": "2025",
        "return_from": "3",
        "return_to": "5",
        "return_month": "May",
        "return_year": "2025",
        "currency": "USD",
        "max_results": "200",
        "max_budget": "100",
    },
    {
        "name": "تل أبيب 21 - 26 مايو",
        "trip_type": "Return",
        "origin": "Tel Aviv",
        "depart_from": "21",
        "depart_to": "23",
        "depart_month": "May",
        "depart_year": "2025",
        "return_from": "24",
        "return_to": "26",
        "return_month": "May",
        "return_year": "2025",
        "currency": "USD",
        "max_results": "200",
        "max_budget": "100",
    },
    {
        "name": "تل أبيب 28 - 31 مايو",
        "trip_type": "Return",
        "origin": "Tel Aviv",
        "depart_from": "28",
        "depart_to": "30",
        "depart_month": "May",
        "depart_year": "2025",
        "return_from": "31",
        "return_to": "31",
        "return_month": "May",
        "return_year": "2025",
        "currency": "USD",
        "max_results": "200",
        "max_budget": "100",
    },
    {
        "name": "تل أبيب 28 مايو - 2 يونيو",
        "trip_type": "Return",
        "origin": "Tel Aviv",
        "depart_from": "28",
        "depart_to": "30",
        "depart_month": "May",
        "depart_year": "2025",
        "return_from": "1",
        "return_to": "2",
        "return_month": "Jun",
        "return_year": "2025",
        "currency": "USD",
        "max_results": "200",
        "max_budget": "100",
    },
    {
        "name": "تل أبيب 7 - 15 يونيو",
        "trip_type": "Return",
        "origin": "Tel Aviv",
        "depart_from": "7",
        "depart_to": "15",
        "depart_month": "Jun",
        "depart_year": "2025",
        "return_from": "7",
        "return_to": "15",
        "return_month": "Jun",
        "return_year": "2025",
        "currency": "USD",
        "max_results": "200",
        "max_budget": "100",
    },
]

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
                break  # تجاهل النتيجة بالكامل
            route_summary += f"<b>{date.strip()}</b>\n🕒 {time.strip()}\n✈️ {route.strip()}\n\n"
        else:
            # فقط إذا لم يتم التخطي لأي جزء
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
