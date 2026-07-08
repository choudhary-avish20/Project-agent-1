"""
mock_injector.py

Takes the pages/ + fixtures/ output from capture.py and produces a dist/
copy of each page with a mock layer injected. The mock layer overrides
window.fetch and XMLHttpRequest so that, at runtime, any request the
original app's JS makes gets matched (by method + path, ignoring origin
so it works regardless of what port you serve the clone from) against
the recorded fixtures and replayed from there instead of hitting a real
backend.
"""

import json
from pathlib import Path
from urllib.parse import urlsplit
from bs4 import BeautifulSoup

OUTPUT_DIR = Path("site-cloning/clone_output")
PAGES_DIR = OUTPUT_DIR / "pages"
FIXTURES_DIR = OUTPUT_DIR / "fixtures"
DISTR_DIR = OUTPUT_DIR / "distr"

# Template for the injected mock layer. {FIXTURES_JSON} is filled in per-page.
MOCK_SCRIPT_TEMPLATE = """
(function () {
  const FIXTURES = %s;

  function keyFor(url, method) {
    const u = new URL(url, location.href);
    return (method || 'GET').toUpperCase() + ' ' + u.pathname + u.search;
  }

  function lookup(url, method) {
    const fixture = FIXTURES[keyFor(url, method)];
    if (!fixture) {
      console.warn('[clone-mock] no fixture for', method, url);
    }
    return fixture;
  }

  // --- main override
  const originalFetch = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : input.url;
    const method = (init && init.method) || (typeof input !== 'string' && input.method) || 'GET';
    const fixture = lookup(url, method);
    if (!fixture) {
      return Promise.resolve(new Response('{}', { status: 404, statusText: 'No fixture recorded' }));
    }
    return Promise.resolve(
      new Response(fixture.body ?? '', {
        status: fixture.status,
        headers: fixture.headers || {},
      })
    );
  };

  // --- XMLHttpRequest override (minimal shim) ---
  const OriginalXHR = window.XMLHttpRequest;
  function MockXHR() {
    const xhr = new OriginalXHR();
    let _url, _method;
    const open = xhr.open.bind(xhr);
    xhr.open = function (method, url, ...rest) {
      _url = url;
      _method = method;
      return open(method, url, ...rest);
    };
    const send = xhr.send.bind(xhr);
    xhr.send = function (...args) {
      const fixture = lookup(_url, _method);
      setTimeout(() => {
        Object.defineProperty(xhr, 'status', { value: fixture ? fixture.status : 404, configurable: true });
        Object.defineProperty(xhr, 'responseText', { value: fixture ? fixture.body : '{}', configurable: true });
        Object.defineProperty(xhr, 'readyState', { value: 4, configurable: true });
        xhr.dispatchEvent(new Event('readystatechange'));
        xhr.dispatchEvent(new Event('load'));
      }, 0);
    };
    return xhr;
  }
  window.XMLHttpRequest = MockXHR;
})();
"""


def build_fixture_map(fixtures: list[dict]) -> dict:
    """Collapse recorded fixtures into a method+path -> {status, headers, body} map."""
    fixture_map = {}
    for f in fixtures:
        path = urlsplit(f["url"]).path
        query = urlsplit(f["url"]).query
        key = f"{f['method'].upper()} {path}" + (f"?{query}" if query else "")
        if key in fixture_map:
            continue  # keep the first recorded response for duplicate calls
        fixture_map[key] = {
            "status": f["status"],
            "headers": f["headers"],
            "body": f["body"],
        }
    return fixture_map


def inject_page(slug: str) -> None:
    html_path = PAGES_DIR / f"{slug}.html"
    fixtures_path = FIXTURES_DIR / f"{slug}.json"

    html = html_path.read_text(encoding="utf-8")
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8")) if fixtures_path.exists() else []
    fixture_map = build_fixture_map(fixtures)

    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.new_tag("script")
    script_tag.string = MOCK_SCRIPT_TEMPLATE % json.dumps(fixture_map)

    if soup.head:
        soup.head.insert(0, script_tag)  # must run before the app's own scripts
    else:
        soup.insert(0, script_tag)

    DISTR_DIR.mkdir(parents=True, exist_ok=True)
    (DISTR_DIR / f"{slug}.html").write_text(str(soup), encoding="utf-8")
    print(f"[{slug}] injected {len(fixture_map)} mocked endpoints")


def main():
    slugs = [p.stem for p in PAGES_DIR.glob("*.html")]
    if not slugs:
        print(f"No pages found in {PAGES_DIR}. Run capture.py first.")
        return
    for slug in slugs:
        inject_page(slug)
    print(f"\nDone. Mocked pages in {DISTR_DIR.resolve()}")


if __name__ == "__main__":
    main()