"""
testing.py

verifynig if the mock js correctly matches the requests by copied frontend
"""

from pathlib import Path
from playwright.sync_api import sync_playwright, Page

BASE_URL = "http://localhost:8080"
DIST_DIR = Path("site-cloning/clone_output/distr")
CLICK_INTERACTIONS = True
CLICK_WAIT_MS = 500


def verify_page(page: Page, slug: str) -> list[str]:
    warnings: list[str] = []
    start_url = f"{BASE_URL}/{slug}.html"

    def on_console(msg):
        if "[clone-mock] no fixture for" in msg.text:
            warnings.append(msg.text)

    page.on("console", on_console)
    page.goto(start_url, wait_until="networkidle")

    if CLICK_INTERACTIONS:
        handles = page.query_selector_all("[data-agent-id]")
        for h in handles:
            try:
                if not h.is_visible():
                    continue
                h.click(timeout=1000)
                page.wait_for_timeout(CLICK_WAIT_MS)
                # un-stitched links may navigate away entirely (step 5 isn't done yet) — recover
                if page.url != start_url:
                    page.goto(start_url, wait_until="networkidle")
            except Exception:
                pass  # not every tagged element is safely clickable in isolation

    page.remove_listener("console", on_console)
    return warnings


def main():
    slugs = [p.stem for p in DIST_DIR.glob("*.html")]
    if not slugs:
        print(f"No pages found in {DIST_DIR}. Run capture.py + mock_injector.py first.")
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()

        any_missing = False
        for slug in slugs:
            warnings = verify_page(page, slug)
            if warnings:
                any_missing = True
                print(f"\n[{slug}] {len(warnings)} missing fixture(s) surfaced:")
                for w in sorted(set(warnings)):
                    print(f"   {w}")
            else:
                print(f"[{slug}] all triggered requests matched a fixture")

        browser.close()

    if any_missing:
        print("\nSome interactions have no recorded fixture — re-run capture.py while "
              "manually performing those actions so they get captured, or ignore if "
              "those endpoints aren't needed for the demo flow.")


if __name__ == "__main__":
    main()