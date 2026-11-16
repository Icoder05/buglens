"""Capture README screenshots of the running demo (http://127.0.0.1:7860) with local Edge.

Run:  uv run --with playwright==1.49.1 python scripts/take_screenshots.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:7860/"


def wait_done(page, timeout=240000):
    """Wait until Gradio's 'processing | 12.3s' indicators are gone."""
    page.wait_for_timeout(2000)
    page.wait_for_function("() => !document.body.innerText.includes('processing |')",
                           timeout=timeout)


def shot(page, name, top, height, width=1400):
    page.screenshot(path=str(OUT / name), full_page=True,
                    clip={"x": 0, "y": top, "width": width, "height": height})


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 1000})
    page.goto(URL)
    page.wait_for_selector("svg .node", timeout=120000)
    page.wait_for_timeout(1500)
    # 1. Localize: issue, ranked functions with gold marks, source
    shot(page, "localize_tab.png", 0, 1080)

    # 2. Paste an issue -> live ranking
    page.get_by_text("…or paste an issue for a pre-indexed repo").click()
    page.get_by_label("Issue text").fill(
        "Blueprint names containing a dot should raise a ValueError instead of an assert")
    page.get_by_role("button", name="Localize").click()
    wait_done(page)
    page.wait_for_timeout(1500)
    box = page.get_by_role("button", name="Localize").bounding_box()
    page.evaluate("window.scrollTo(0, 0)")
    top = page.evaluate("(y) => y + window.scrollY", box["y"]) if box else 0
    shot(page, "localize_paste_issue.png", max(0, top - 330), 900)

    # 3. Onboard: Ask the codebase -> cited answer
    page.get_by_role("tab", name="Onboard").click()
    page.wait_for_timeout(2500)
    page.get_by_label("Ask the codebase").fill("where are blueprints registered?")
    page.get_by_role("button", name="Ask").click()
    wait_done(page)
    page.wait_for_timeout(1500)
    ask = page.get_by_label("Ask the codebase").bounding_box()
    y = page.evaluate("(y) => y + window.scrollY", ask["y"])
    shot(page, "ask_the_codebase.png", max(0, y - 30), 620)

    # 4. Onboard: cited onboarding guide
    guide = page.locator("h1:has-text('Onboarding guide')").first
    guide.scroll_into_view_if_needed()
    gb = guide.bounding_box()
    y = page.evaluate("(y) => y + window.scrollY", gb["y"])
    shot(page, "onboarding_guide.png", max(0, y - 20), 760)
    browser.close()
print("saved to", OUT)
