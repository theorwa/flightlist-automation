# flightlist_scraper.py
# Multi-filter configurable FlightList.io scraper with Telegram alerts

import asyncio
import os
import httpx
from playwright.async_api import async_playwright

# ========== Filters Configuration ==========
FILTERS = [
    {
        "name": "بوخارست بين 10 و 12 مايو ≥ 25$ ",
        "origin": "Bucharest",
        "depart_day": "10",
        "return_day": "12",
        "currency": "USD",
        "max_results": "25",
        "max_budget": "25",
    },
    # {
    #     "name": "صوفيا بين 15 و 17 مايو",
    #     "origin": "Sofia",
    #     "depart_day": "15",
    #     "return_day": "17",
    #     "currency": "USD",
    #     "max_results": "25",
    #     "max_budget": "25",
    # }
    # أضف المزيد هنا 👆
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

    await page.locator('#deprange').click()
    await page.wait_for_selector('.daterangepicker', timeout=3000)
    await page.locator(f'td:has-text("{config["depart_day"]}")').nth(1).click()
    await page.locator(f'td:has-text("{config["return_day"]}")').nth(1).click()
    await page.locator('.applyBtn:enabled').click()

    await page.select_option('#currency', config['currency'])
    await page.locator('button:has-text("Additional Options")').click()
    await page.wait_for_selector('#limit', timeout=2000)
    await page.select_option('#limit', config['max_results'])
    await page.fill('#budget', config['max_budget'])

    await page.locator('#submit').click()
    await page.wait_for_timeout(2000)

    await page.wait_for_selector(".flights-list .flight", timeout=20000)
    flight_cards = page.locator(".flights-list .flight")
    count = await flight_cards.count()
    results = []

    for i in range(count):
        flight = flight_cards.nth(i)
        price = await flight.locator(".price").inner_text()
        date = await flight.locator("div.col-md-3 small.text-muted").inner_text()
        route = await flight.locator(".col-md-5 small.text-muted").inner_text()
        times = await flight.locator(".col-md-3 span.reduced").inner_text()
        results.append(
            f"<b>{date}</b>\n🕒 {times.strip()}\n✈️ {route.strip()}\n💰 Price: <b>${price}</b>\n---"
        )

    if results:
        header = f"🧭 <b>{config['name']}</b>\n\n"
        await send_telegram_message(header + "\n\n".join(results))
        print(f"[SUCCESS] Sent {len(results)} results to Telegram.")
    else:
        print("[INFO] No results found for this filter.")

# ========== Runner ==========
async def run():
    print("[INFO] Launching browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
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
