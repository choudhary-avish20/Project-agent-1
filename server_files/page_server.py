"""
page_server.py — serves the clone's distr/ folder on port 8080.

    uvicorn page_server:app --host 0.0.0.0 --port 8080
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

DIST_DIR = Path(__file__).resolve().parent.parent / "site-cloning" / "clone_output" / "distr"

app = FastAPI()
app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="static")
