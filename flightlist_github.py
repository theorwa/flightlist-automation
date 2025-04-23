# flightlist_poc.py
# Extracts cheapest flights from FlightList.io and sends to Telegram (final version)

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
        origin_input = page.locator('#from-input')
        await origin_input.wait_for(timeout=10000)
        await origin_input.click()
        await page.keyboard.type("Bucharest", delay=100)
        await page.wait_for_timeout(1000)

        for i in range(10):
            items = await page.locator(".easy-autocomplete-container .eac-item").all()
            if items:
                await items[0].click()
                print("[SUCCESS] Selected: Bucharest from autocomplete")
                break
            else:
                print(f"[WAIT] Autocomplete not ready yet... retry {i + 1}")
                await page.wait_for_timeout(500)
        else:
            raise Exception("Autocomplete list did not appear after multiple attempts")

        print("[INFO] Selecting departure date range: May 10 - May 12")
        await page.locator('#deprange').click()
        await page.wait_for_selector('.daterangepicker', timeout=5000)
        await page.locator('td:has-text("10")').nth(1).click()
        await page.locator('td:has-text("12")').nth(1).click()
        await page.locator('.applyBtn:enabled').click()
        await page.wait_for_timeout(1000)

        print("[INFO] Selecting currency: USD")
        await page.select_option('#currency', 'USD')

        print("[INFO] Expanding additional options")
        await page.locator('button:has-text("Additional Options")').click()
        await page.wait_for_timeout(1000)

        print("[INFO] Setting max number of results to 25")
        await page.select_option('#limit', '25')

        print("[INFO] Setting maximum budget to 27 USD")
        await page.fill('#budget', '27')
        await page.wait_for_timeout(500)

        print("[INFO] Clicking the Search button")
        await page.locator('#submit').click()
        await page.wait_for_timeout(5000)

        print("[INFO] Waiting for results to load...")
        await page.wait_for_selector(".flights-list .flight", timeout=30000)

        print("[INFO] Extracting flight deals...")
        flight_cards = page.locator(".flights-list .flight")
        count = await flight_cards.count()
        results = []

        for i in range(count):
            flight = flight_cards.nth(i)
            price = await flight.locator(".price").inner_text()
            date = await flight.locator("div.col-md-3 small.text-muted").inner_text()
            route = await flight.locator(".col-md-5 small.text-muted").inner_text()
            times = await flight.locator(".col-md-3 span.reduced").inner_text()
            results.append(f"<b>{date}</b>\n🕒 {times.strip()}\n✈️ {route.strip()}\n💰 Price: <b>${price}</b>\n---")

        if results:
            content = "\n\n".join(results)
            print("[INFO] Sending to Telegram...")
            await send_telegram_message(content)
            print("[SUCCESS] Message sent to Telegram.")
        else:
            print("[INFO] No flights found. Nothing to send.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
