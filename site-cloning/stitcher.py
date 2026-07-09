"""
stitcher.py

Takes the mocked pages in clone_output/dist and:
  1. Rewrites any <a href> that points at a known captured route (whether
     absolute, matching BASE_URL, or relative) to the corresponding local
     filename (e.g. "/pricing" -> "pricing.html").
  2. Injects a capture-phase click guard that force-navigates for any of
     those local links. This matters if the original site does
     client-side routing (React Router, etc.) — the framework's own click
     handler would otherwise intercept the click and try to "route" to a
     page it doesn't have. A listener on `document` registered with
     capture=true always runs before any handler further down the tree,
     regardless of when the framework registered its own, so this reliably
     wins and forces a real page load to our local file instead.
  3. Leaves anything pointing elsewhere (external links) untouched.

Run (after capture.py and mock_injector.py have produced clone_output/dist):
    python stitcher.py
"""

import json
from pathlib import Path
from urllib.parse import urlsplit
from bs4 import BeautifulSoup

# Keep these in sync with capture.py
BASE_URL = "http://localhost:3000"
ROUTES = ["/", "/collections", "/about", "/contact", "/custom-orders", "/product/:id"]
DIST_DIR = Path("site-cloning/clone_output") / "distr"

NAV_GUARD_TEMPLATE = """
(function () {
  const LOCAL_PAGES = new Set(%s);
  document.addEventListener('click', function (e) {
    const a = e.target.closest('a[href]');
    if (!a) return;
    const href = a.getAttribute('href');
    if (href && LOCAL_PAGES.has(href)) {
      e.preventDefault();
      e.stopImmediatePropagation();
      window.location.href = href;
    }
  }, true);
})();
"""


def slug_for_route(route: str) -> str:
    if route == "/":
        return "index"
    return route.strip("/").replace("/", "_")


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path


ROUTE_TO_FILENAME = {normalize_path(r): f"{slug_for_route(r)}.html" for r in ROUTES}


def resolve_local_href(href: str) -> str | None:
    if href.startswith("http://") or href.startswith("https://"):
        if not href.startswith(BASE_URL):
            return None  # external site, leave it alone
        path = href[len(BASE_URL):]
    else:
        path = href
    path = path.split("#")[0].split("?")[0]
    return ROUTE_TO_FILENAME.get(normalize_path(path))


def stitch_page(html_path: Path) -> int:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    rewritten = 0
    for a in soup.find_all("a", href=True):
        local_target = resolve_local_href(a["href"])
        if local_target:
            a["href"] = local_target
            rewritten += 1

    guard_script = soup.new_tag("script")
    guard_script.string = NAV_GUARD_TEMPLATE % json.dumps(list(ROUTE_TO_FILENAME.values()))
    if soup.head:
        soup.head.insert(0, guard_script)
    else:
        soup.insert(0, guard_script)

    html_path.write_text(str(soup), encoding="utf-8")
    return rewritten


def main():
    files = list(DIST_DIR.glob("*.html"))
    if not files:
        print(f"No pages found in {DIST_DIR}. Run capture.py + mock_injector.py first.")
        return
    for f in files:
        count = stitch_page(f)
        print(f"[{f.name}] rewrote {count} internal link(s)")
    print(f"\nDone. {DIST_DIR.resolve()} is now a self-contained, navigable bundle.")


if __name__ == "__main__":
    main()