#!/usr/bin/env python3
"""
Playwright-based verification of the SPA Personality page.
Navigates to /command, sets auth, then uses JS hash routing
to reach #/personality. Verifies tabs, sliders, Per-Operator UI.
"""

import os
import sys
import asyncio
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

import httpx
from playwright.async_api import async_playwright

BASE = "http://localhost:8000"
TOKEN = os.environ.get("HUB_TOKEN", "dev-token-insecure")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )

        page = await context.new_page()
        console_logs = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: console_logs.append(f"[PAGE_ERROR] {err}"))

        # Step 1: Navigate to /command (the SPA entry point, no hash)
        print("Step 1: Navigate to /command...")
        try:
            resp = await page.goto(f"{BASE}/command", wait_until="domcontentloaded", timeout=20000)
            print(f"  HTTP {resp.status if resp else 'N/A'}")
        except Exception as e:
            print(f"  Navigation error: {e}")

        await asyncio.sleep(3)

        # Step 2: Set auth token in localStorage
        print(f"\nStep 2: Set hub_token in localStorage...")
        await page.evaluate(f"""
            localStorage.setItem('hub_token', '{TOKEN}');
        """)
        # Also set cookie
        await page.evaluate(f"""
            document.cookie = "empire_session={TOKEN}; path=/; max-age=3600; SameSite=Lax";
        """)
        print("  Token set")

        # Step 3: Reload SPA so it initializes with auth
        print("\nStep 3: Reload SPA...")
        await page.goto(f"{BASE}/command", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        # Wait for the SPA to render (look for the root element)
        try:
            await page.wait_for_function("document.getElementById('root')?.children?.length > 0", timeout=10000)
            print("  SPA root rendered")
        except Exception:
            print("  SPA root may be empty or still loading")

        await asyncio.sleep(2)

        # Step 4: Navigate to personality via hash
        print("\nStep 4: Navigate to #/personality...")
        await page.evaluate("window.location.hash = '#/personality'")
        await asyncio.sleep(3)

        # Wait for the hash router to process
        try:
            await page.wait_for_function(
                "() => window.location.hash.includes('personality')", 
                timeout=5000
            )
        except Exception:
            pass

        print(f"  Hash: {await page.evaluate('window.location.hash')}")

        # Step 5: Take screenshot
        await page.screenshot(path="/tmp/spa_initial.png", full_page=True)
        print("  Screenshot: /tmp/spa_initial.png")

        # Step 6: Extract page content
        body_text = await page.inner_text("body")
        print(f"\nBody text (first 2000 chars):\n{body_text[:2000]}\n")

        # ── VERIFICATION ──
        all_pass = True
        results = []

        def check(name, condition, detail=""):
            nonlocal all_pass
            status = "PASS" if condition else "FAIL"
            if not condition:
                all_pass = False
            results.append({"name": name, "status": status, "detail": detail})
            print(f"  [{status}] {name} {detail}")

        section = lambda s: print(f"\n--- {s} ---")

        # TABS
        section("TABS")
        tabs = ["Configuration", "Profiles", "Per-Operator", "History"]
        for t in tabs:
            check(f"Tab '{t}' visible", t.lower() in body_text.lower())

        # CONTENT
        section("CONTENT")
        check("Personality heading", "Personality" in body_text)
        check("Aggressive profile", "Aggressive" in body_text)
        check("Conservative profile", "Conservative" in body_text)
        check("Balanced profile", "Balanced" in body_text)
        check("Niche: Roofing Restoration", "Roofing Restoration" in body_text)
        check("Niche: Storm Damage", "Storm Damage" in body_text)
        check("Threshold values", any(w in body_text for w in ["0.40", "0.75", "0.60", "threshold"]))
        check("Temperature values", any(w in body_text for w in ["0.25", "0.05", "0.10", "temperature"]))

        # SLIDERS
        section("SLIDERS")
        sliders = await page.query_selector_all("input[type='range']")
        check(f"Range slider count ({len(sliders)})", len(sliders) > 0, f"found {len(sliders)}")
        for i, s in enumerate(sliders):
            min_v = await s.get_attribute("min") or "?"
            max_v = await s.get_attribute("max") or "?"
            val = await s.get_attribute("value") or "?"
            print(f"    Slider {i}: min={min_v} max={max_v} value={val}")

        # Click each slider and verify value changes
        for i, s in enumerate(sliders):
            try:
                val_before = await s.get_attribute("value")
                # Use JS to change the value
                await s.fill("0.50")
                # Also try via JS evaluation
                await s.evaluate("el => { el.value = '0.50'; el.dispatchEvent(new Event('input', { bubbles: true })); }")
                await asyncio.sleep(0.5)
                val_after = await s.get_attribute("value")
                print(f"    Slider {i}: {val_before} → {val_after}")
            except Exception as e:
                print(f"    Slider {i}: could not interact - {e}")

        # PER-OPERATOR TAB ELEMENTS
        section("PER-OPERATOR")
        per_op_keywords = ["Operator", "operator_id", "Global Override", "Active Overrides", "Remove"]
        for kw in per_op_keywords:
            check(f"Per-Operator: '{kw}' in text", kw.lower() in body_text.lower())

        # Click the Per-Operator tab if possible
        all_buttons = await page.query_selector_all("button")
        print(f"\n  Total buttons: {len(all_buttons)}")
        for btn in all_buttons:
            try:
                txt = await btn.inner_text()
                if "per-operator" in txt.lower() or "operator" in txt.lower():
                    await btn.click()
                    await asyncio.sleep(2)
                    await page.screenshot(path="/tmp/spa_tab_per_operator.png", full_page=True)
                    print("  Clicked Per-Operator tab → screenshot saved")
                    
                    # Check for sliders in Per-Operator view
                    po_sliders = await page.query_selector_all("input[type='range']")
                    print(f"  Sliders in Per-Operator: {len(po_sliders)}")
                    
                    # Check for Operator ID input
                    text_inputs = await page.query_selector_all("input[type='text'], input:not([type])")
                    print(f"  Text inputs: {len(text_inputs)}")
                    break
            except Exception as e:
                print(f"  Error clicking button: {e}")

        # CONSOLE ERRORS
        section("CONSOLE")
        js_errors = [l for l in console_logs if "error" in l.lower() or "PAGE_ERROR" in l]
        other_logs = [l for l in console_logs if l not in js_errors]
        check("JS errors", len(js_errors) == 0, f"found {len(js_errors)}")
        for err in js_errors[:5]:
            print(f"    {err}")
        if other_logs:
            print(f"  Other logs ({len(other_logs)}):")
            for log in other_logs[:5]:
                print(f"    {log}")

        # SUMMARY
        section("SUMMARY")
        passed = sum(1 for r in results if r["status"] == "PASS")
        failed = sum(1 for r in results if r["status"] == "FAIL")
        print(f"  Passed: {passed}/{len(results)}")
        print(f"  Failed: {failed}/{len(results)}")
        print(f"  Sliders: {len(sliders)}")
        print(f"  Overall: {'✅ ALL CHECKS PASSED' if all_pass else '⚠️ SOME FAILED'}")
        print(f"\nScreenshots:")
        print(f"  /tmp/spa_initial.png")
        print(f"  /tmp/spa_tab_per_operator.png")

        await browser.close()
        return all_pass


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
