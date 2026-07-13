# branch1_agent — LiveKit Voice Demo Agent

An AI voice agent that gives a live, guided demo of a cloned website. The agent speaks to visitors, navigates pages, clicks elements, and responds to questions using LiveKit for real-time voice and a data channel for browser control.

---

## How It Works

```
capture.py → mock_js_injector.py → stitcher.py → runtimer_injector.py
                                                        ↓
                                              distr/  (static clone)
                                                        ↓
                                  page_server.py  +  token_server.py  +  orchestrator.py
```

1. **`site-cloning/capture.py`** — Visits the live React app with Playwright, tags interactive elements with `data-agent-id`, and saves rendered HTML + XHR fixtures.
2. **`site-cloning/mock_js_injector.py`** — Injects a mock fetch/XHR layer into each page so it runs without a backend.
3. **`site-cloning/stitcher.py`** — Rewrites internal links to local filenames so navigation works as a static bundle.
4. **`server_files/runtimer_injector.py`** — Injects `agent-runtime.js` and `chat-ui.js` into every page in `distr/`.

---

## Running the Agent

Make sure you have a `.env` file with `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `OPENAI_API_KEY` (+ Deepgram/Cartesia keys if needed).

```bash
# 1. Token server — generates short-lived LiveKit join tokens (port 8081)
source venv/bin/activate && cd server_files && uvicorn token_server:app --host 0.0.0.0 --port 8081

# 2. Page server — serves the static clone (port 8080)
source venv/bin/activate && cd server_files && uvicorn page_server:app --host 0.0.0.0 --port 8080

# 3. Orchestrator — the LLM voice agent (run from project root)
source venv/bin/activate && python server_files/orchestrator.py dev
```

Then open `http://localhost:8080` in your browser, grant mic permission, and talk to the agent.

---

## Project Structure

```
branch1_agent/
├── server_files/
│   ├── orchestrator.py        # LLM agent — joins LiveKit room, drives the demo
│   ├── agent_runtime.js       # Injected into clone pages; executes agent commands
│   ├── chat_ui.js             # Chat sidebar injected into clone pages
│   ├── token_server.py        # FastAPI: issues LiveKit access tokens
│   ├── page_server.py         # FastAPI: serves the distr/ static bundle
│   ├── runtimer_injector.py   # Pipeline step: injects JS into distr/ pages
│   └── pages-flow.json        # Scripted demo walkthrough (steps, goals, talking points)
├── site-cloning/
│   ├── capture.py             # Pipeline step 1: capture + tag
│   ├── mock_js_injector.py    # Pipeline step 2: mock XHR/fetch
│   ├── stitcher.py            # Pipeline step 3: rewrite internal links
│   ├── testing.py             # Verify mock coverage with Playwright
│   └── clone_output/
│       ├── pages/             # Raw captured HTML
│       ├── fixtures/          # Recorded XHR/fetch responses
│       └── distr/             # Final deployable static clone
├── chat-ui-testing/           # Isolated sandbox for testing the chat UI
└── demo-site/                 # Original React SPA (gitignored)
```
