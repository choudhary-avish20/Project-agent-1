"""
capture.py — steps 1-3 of the clone capture pipeline.

For each route on the target site, this:
  1. Records every XHR/fetch request+response as a JSON fixture
     (so step 4 can replay them without hitting the live backend).
  2. Tags interactive elements in the live DOM with a stable `data-agent-id`
     (so the orchestrator has durable handles to target later).
  3. Saves the resulting tagged, rendered HTML.

Run:
    pip install playwright --break-system-packages
    playwright install chromium
    python capture.py
"""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Response

# ---- config: point this at your test site ----
BASE_URL = "http://localhost:3000"
ROUTES = ["/", "/pricing", "/about"]
OUTPUT_DIR = Path("clone_output")

# Elements we consider "interactive" and worth tagging for the agent.
INTERACTIVE_SELECTOR = "a, button, input, select, textarea, [role='button'], [onclick]"

# Runs inside the page, before we grab page.content(), so the
# data-agent-id attributes end up baked into the captured HTML.
TAG_SCRIPT = """
(selector) => {
  const els = document.querySelectorAll(selector);
  let count = 0;
  els.forEach((el) => {
    if (el.hasAttribute('data-agent-id')) return;
    const role = el.getAttribute('role') || el.tagName.toLowerCase();
    const raw = el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
    const text = raw.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 30);
    const id = `${role}-${text || count}`;
    el.setAttribute('data-agent-id', id);
    count++;
  });
  return count;
}
"""


def slug_for_route(route: str) -> str:
    if route == "/":
        return "index"
    return route.strip("/").replace("/", "_")


def capture_route(page: Page, route: str) -> tuple[str, list[dict], int]:
    fixtures: list[dict] = []

    def on_response(response: Response):
        req = response.request
        if req.resource_type not in ("xhr", "fetch"):
            return
        try:
            body = response.text()
        except Exception:
            body = None
        fixtures.append({
            "url": req.url,
            "method": req.method,
            "status": response.status,
            "headers": dict(response.headers),
            "body": body,
        })

    page.on("response", on_response)
    page.goto(BASE_URL + route, wait_until="networkidle")

    tagged_count = page.evaluate(TAG_SCRIPT, INTERACTIVE_SELECTOR)
    html = page.content()

    page.remove_listener("response", on_response)
    return html, fixtures, tagged_count


def main():
    (OUTPUT_DIR / "pages").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "fixtures").mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context()

        for route in ROUTES:
            page = context.new_page()
            html, fixtures, tagged_count = capture_route(page, route)
            page.close()

            slug = slug_for_route(route)
            (OUTPUT_DIR / "pages" / f"{slug}.html").write_text(html, encoding="utf-8")
            (OUTPUT_DIR / "fixtures" / f"{slug}.json").write_text(
                json.dumps(fixtures, indent=2), encoding="utf-8"
            )
            print(f"[{route}] tagged {tagged_count} elements, recorded {len(fixtures)} fixtures")

        browser.close()

    print(f"\nDone. Output in {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()