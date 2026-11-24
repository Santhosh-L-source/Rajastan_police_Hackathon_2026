#!/usr/bin/env python3
"""Capture presentation screenshots of FINTRACE app.

Captures 4 screenshots at 1920x1080:
  01  Money Trail Graph  – a HIGH-risk (red) node selected, side panel open
  02  Freeze Priority    – table + recovery curve
  03  Infrastructure     – cluster cards
  04  AI Assistant       – pre-populated question + response
"""

import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = Path("docs/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


async def capture_screenshots():
    async with async_playwright() as p:
        print("Launching browser…")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        try:
            print("Loading FINTRACE app…")
            await page.goto("http://localhost:3001", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            # Select case_001
            print("Selecting case_001…")
            case_link = page.locator("text=case_001").first
            if await case_link.is_visible():
                await case_link.click()
            await page.wait_for_timeout(5000)

            # ── Screenshot 1: Money Trail Graph ──
            # Click the first HIGH-risk (red) node.
            # Cytoscape nodes are inside a canvas, so we use page.evaluate.
            print("Clicking a HIGH-risk node…")
            await page.evaluate("""() => {
                const cy = document.querySelector('[class*="cytoscape"]')?.__cy
                    || window.__cy;
                if (!cy) {
                    // fallback: look for the cytoscape container
                    const containers = document.querySelectorAll('div');
                    for (const c of containers) {
                        if (c._cyreg) { window.__cy = c._cyreg.cy; break; }
                    }
                }
            }""")
            await page.wait_for_timeout(1000)

            # Click a red node via Cytoscape API
            clicked = await page.evaluate("""() => {
                // react-cytoscapejs stores cy in the div's _cyreg
                const divs = document.querySelectorAll('div');
                let cy = null;
                for (const d of divs) {
                    if (d._cyreg && d._cyreg.cy) { cy = d._cyreg.cy; break; }
                }
                if (!cy) return false;
                const highNodes = cy.nodes().filter(n => n.data('risk_level') === 'HIGH');
                if (highNodes.length === 0) return false;
                highNodes[0].select();
                highNodes[0].emit('tap');
                return true;
            }""")

            if not clicked:
                # Fallback: click centre of the graph canvas
                print("  (fallback: clicking canvas centre)")
                canvas = page.locator("canvas").first
                if await canvas.is_visible():
                    box = await canvas.bounding_box()
                    if box:
                        await page.mouse.click(box["x"] + box["width"] * 0.35, box["y"] + box["height"] * 0.4)
            await page.wait_for_timeout(2000)

            await page.screenshot(path=str(SCREENSHOTS_DIR / "01_money_trail_graph.png"), full_page=False)
            print("  OK Saved: 01_money_trail_graph.png")

            # ── Screenshot 2: Freeze Priority ──
            print("Navigating to Freeze Priority…")
            await page.click("text=Freeze Priority")
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "02_freeze_priority.png"), full_page=False)
            print("  OK Saved: 02_freeze_priority.png")

            # ── Screenshot 3: Infrastructure ──
            print("Navigating to Infrastructure…")
            await page.click("text=Infrastructure")
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "03_infrastructure.png"), full_page=False)
            print("  OK Saved: 03_infrastructure.png")

            # ── Screenshot 4: AI Assistant ──
            print("Navigating to AI Assistant…")
            await page.click("text=AI Assistant")
            await page.wait_for_timeout(2000)

            # Type a question and submit
            print("Submitting AI query…")
            input_sel = 'input[type="text"]'
            await page.fill(input_sel, "Who are the top 3 accounts to freeze and why?")
            await page.wait_for_timeout(500)
            await page.click('button:has-text("Ask")')
            await page.wait_for_timeout(5000)

            await page.screenshot(path=str(SCREENSHOTS_DIR / "04_ai_assistant.png"), full_page=False)
            print("  OK Saved: 04_ai_assistant.png")

        except Exception as e:
            print(f"\nX Screenshot capture failed: {e}")
            # Save a debug screenshot
            await page.screenshot(path=str(SCREENSHOTS_DIR / "debug_error.png"), full_page=False)
            await browser.close()
            sys.exit(1)

        await browser.close()
        print(f"\nOK All screenshots captured → {SCREENSHOTS_DIR.absolute()}")


if __name__ == "__main__":
    asyncio.run(capture_screenshots())
