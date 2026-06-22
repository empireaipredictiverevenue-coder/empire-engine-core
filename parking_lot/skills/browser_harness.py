"""
EMPIRE AI · BROWSER HARNESS SKILL
==================================
Wraps dev-browser (github.com/SawyerHood/dev-browser) as a Hermes skill
for autonomous browser-based research, scraping, and testing.

Part of the recursive self-healing loop architecture.
"""

import os
import json
import subprocess
import logging
from typing import Optional, List, Dict, Any

log = logging.getLogger("empire.browser_harness")

DEV_BROWSER_PATH = os.environ.get("DEV_BROWSER_PATH", "/root/dev-browser")
DEV_BROWSER_CLI = os.path.join(DEV_BROWSER_PATH, "cli")


def run_browser_script(
    script_path: str,
    url: Optional[str] = None,
    timeout: int = 60,
    headless: bool = True,
) -> Dict[str, Any]:
    """Run a dev-browser script and return results.

    Args:
        script_path: Path to .js script to execute
        url: Optional starting URL (will be passed to script)
        timeout: Max execution time in seconds
        headless: Whether to run headless

    Returns:
        dict with keys: success, output, error, screenshot_path
    """
    try:
        cmd = ["npx", "dev-browser", "run", script_path]
        if url:
            cmd.extend(["--url", url])
        if headless:
            cmd.append("--headless")

        result = subprocess.run(
            cmd,
            cwd=DEV_BROWSER_PATH,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": f"Script timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def scrape_page(url: str, wait_selector: Optional[str] = None) -> Dict[str, Any]:
    """Scrape a page using dev-browser with full JS rendering.

    Args:
        url: Page URL to scrape
        wait_selector: CSS selector to wait for before extracting

    Returns:
        dict with keys: title, text_content, links, screenshots, error
    """
    # Create a temporary scraper script
    script = f"""
    const {{ page }} = await browser.newPage();
    await page.goto('{url}', {{ waitUntil: 'networkidle' }});
    {f"await page.waitForSelector('{wait_selector}');" if wait_selector else ""}
    const title = await page.title();
    const text = await page.evaluate(() => document.body.innerText);
    const links = await page.evaluate(() =>
        Array.from(document.querySelectorAll('a[href]')).map(a => ({{
            text: a.innerText.trim(),
            href: a.href
        }}))
    );
    await page.screenshot({{ path: '/tmp/browser_harness_screenshot.png' }});
    await browser.close();
    return {{ title, text, links }};
    """

    script_path = "/tmp/_browser_scrape.js"
    with open(script_path, "w") as f:
        f.write(script)

    result = run_browser_script(script_path, url=url)

    if result["success"]:
        try:
            output = json.loads(result["output"])
            output["screenshot_path"] = "/tmp/browser_harness_screenshot.png"
            return output
        except json.JSONDecodeError:
            return {"title": "", "text_content": result["output"], "links": [], "error": "parse_failed"}

    return {"title": "", "text_content": "", "links": [], "error": result.get("error")}


def submit_form(
    url: str,
    form_data: Dict[str, str],
    submit_selector: str = "button[type=submit]",
) -> Dict[str, Any]:
    """Fill and submit a form using dev-browser.

    Args:
        url: Form page URL
        form_data: dict of {selector: value} pairs
        submit_selector: CSS selector for submit button

    Returns:
        dict with keys: success, result_url, page_text, error
    """
    pairs = json.dumps(form_data)
    script = f"""
    const {{ page }} = await browser.newPage();
    await page.goto('{url}', {{ waitUntil: 'networkidle' }});
    const fields = {pairs};
    for (const [selector, value] of Object.entries(fields)) {{
        await page.fill(selector, value);
    }}
    await Promise.all([
        page.waitForNavigation({{ waitUntil: 'networkidle' }}),
        page.click('{submit_selector}')
    ]);
    const result_url = page.url();
    const page_text = await page.evaluate(() => document.body.innerText);
    await browser.close();
    return {{ result_url, page_text }};
    """

    script_path = "/tmp/_browser_form.js"
    with open(script_path, "w") as f:
        f.write(script)

    result = run_browser_script(script_path, url=url)

    if result["success"]:
        try:
            return json.loads(result["output"])
        except json.JSONDecodeError:
            return {"success": False, "result_url": "", "page_text": result["output"], "error": "parse_failed"}

    return {"success": False, "result_url": "", "page_text": "", "error": result.get("error")}


def check_browser_harness() -> Dict[str, Any]:
    """Verify dev-browser is installed and working.

    Returns:
        dict with keys: available, version, error
    """
    try:
        result = subprocess.run(
            ["npx", "dev-browser", "--version"],
            cwd=DEV_BROWSER_PATH,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            "available": result.returncode == 0,
            "version": result.stdout.strip() if result.returncode == 0 else None,
            "error": result.stderr if result.returncode != 0 else None,
        }
    except Exception as e:
        return {"available": False, "version": None, "error": str(e)}


# ── Skill Metadata ──────────────────────────────────────────────────────

SKILL_META = {
    "name": "browser.harness",
    "description": "Browser automation for autonomous research — wraps dev-browser with Playwright API",
    "version": "1.0.0",
    "author": "Empire AI",
    "dependencies": ["dev-browser (npm)", "Chrome/Chromium"],
    "capabilities": [
        "scrape_page: Full JS-rendered page scraping",
        "submit_form: Automated form filling and submission",
        "run_script: Execute arbitrary dev-browser scripts",
        "screenshot: Capture page screenshots for visual verification",
        "cua: Computer-use actions (vision-based interaction)",
    ],
    "loop_integration": "Used by autoresearch trading/sniper targets for web-based data collection",
}

if __name__ == "__main__":
    # Test the harness
    status = check_browser_harness()
    print(f"Browser Harness Status: {'✅ Available' if status['available'] else '❌ Unavailable'}")
    if status.get("version"):
        print(f"  Version: {status['version']}")
    if status.get("error"):
        print(f"  Error: {status['error']}")
