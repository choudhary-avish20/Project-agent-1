"""
runtime_injector.py — step 6: wires agent-runtime.js into every page in
clone_output/distr. Run this after capture.py, mock_injector.py, and
stitcher.py.
"""

import shutil
from pathlib import Path
from bs4 import BeautifulSoup

DIST_DIR = Path("site-cloning/clone_output") / "distr"
RUNTIME_SRC = Path("server_files/agent_runtime.js")
CHAT_UI_SRC = Path("server_files/chat_ui.js")
TOKEN_SERVER_URL = "http://localhost:8081" # fire it up before hand

LIVEKIT_CDN = "https://cdn.jsdelivr.net/npm/livekit-client@2/dist/livekit-client.umd.min.js"


def inject(html_path: Path) -> None:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    # Remove existing injected tags to prevent duplicates
    for script in soup.find_all("script"):
        if script.get("src") == LIVEKIT_CDN:
            script.decompose()
        elif script.string and "window.TOKEN_SERVER_URL" in script.string:
            script.decompose()
        elif script.get("src") in ("agent-runtime.js", "agent_runtime.js", "chat-ui.js", "chat_ui.js"):
            script.decompose()

    sdk_tag = soup.new_tag("script", src=LIVEKIT_CDN)
    config_tag = soup.new_tag("script")
    config_tag.string = f'window.TOKEN_SERVER_URL = "{TOKEN_SERVER_URL}";'
    chat_ui_tag = soup.new_tag("script", src="chat-ui.js")
    runtime_tag = soup.new_tag("script", src="agent-runtime.js")

    target = soup.body if soup.body else soup
    target.append(sdk_tag)
    target.append(config_tag)
    target.append(chat_ui_tag)
    target.append(runtime_tag)

    html_path.write_text(str(soup), encoding="utf-8")


def main():
    if not RUNTIME_SRC.exists():
        print(f"{RUNTIME_SRC} not found next to this script.")
        return
    files = list(DIST_DIR.glob("*.html"))
    if not files:
        print(f"No pages found in {DIST_DIR}. Run the earlier pipeline steps first.")
        return

    shutil.copy(RUNTIME_SRC, DIST_DIR / "agent-runtime.js")
    shutil.copy(CHAT_UI_SRC, DIST_DIR / "chat-ui.js")
    
    for f in files:
        inject(f)
        print(f"[{f.name}] runtime wired in and chat is up")

    print(f"\nDone. Start token_server.py and orchestrator.py, then serve {DIST_DIR.resolve()}.")


if __name__ == "__main__":
    main()