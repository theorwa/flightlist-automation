# flightlist_poc.py
# Scrapes FlightList.io and sends results to Telegram (via GitHub Actions)

import asyncio
import json
import os
import httpx
from playwright.async_api import async_playwright

# Send message to Telegram
async def send_telegram_message(message):
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

# Main scraping function
async def run():
    print("[INFO] Launching browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.set_viewport_size({"width": 1920, "height": 1080})

        print("[INFO] Opening FlightList.io...")
        await page.goto("https://www.flightlist.io", wait_until="networkidle")

        print("[INFO] Typing origin: Bucharest and selecting from autocomplete")
        await page.locator('#from-input').click()
        await page.keyboard.type("Bucharest", delay=100)
        await page.wait_for_timeout(1500)

        for _ in range(10):
            items = await page.locator(".easy-autocomplete-container .eac-item").all()
            if items:
                await items[0].click()
                break
            await page.wait_for_timeout(500)

        print("[INFO] Selecting departure date range: May 10 - May 12")
        await page.locator('#deprange').click()
        await page.wait_for_selector('.daterangepicker', timeout=5000)
        await page.locator('td:has-text("10")').nth(1).click()
        await page.locator('td:has-text("12")').nth(1).click()
        await page.locator('.applyBtn:enabled').click()

        print("[INFO] Selecting currency: USD")
        await page.select_option('#currency', 'USD')

        print("[INFO] Expanding additional options")
        await page.locator('button:has-text("Additional Options")').click()

        print("[INFO] Setting max results and budget")
        await page.select_option('#limit', '25')
        await page.fill('#budget', '27')

        print("[INFO] Clicking the Search button")
        await page.locator('#submit').click()
        await page.wait_for_selector(".flights-list .flight", timeout=30000)

        print("[INFO] Extracting results...")
        flights = page.locator(".flights-list .flight")
        count = await flights.count()
        results = []

        for i in range(min(3, count)):
            f = flights.nth(i)
            price = await f.locator(".price").inner_text()
            date = await f.locator("div.col-md-3 small.text-muted").inner_text()
            route = await f.locator(".col-md-5 small.text-muted").inner_text()
            times = await f.locator(".col-md-3 span.reduced").inner_text()
            results.append(f"<b>{date}</b>\n🕒 {times.strip()}\n✈️ {route.strip()}\n💰 Price: <b>${price}</b>\n---")

        content = "\n\n".join(results) or "No flights found."
        print("[INFO] Sending to Telegram...")
        await send_telegram_message(content)
        print("[SUCCESS] Message sent to Telegram.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
