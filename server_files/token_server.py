"""
token_server.py

keeping the api secret from the frontend by generating a token instead of giving the key itself

    uvicorn token_server:app --host 0.0.0.0 --port 8081
"""

import os
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from livekit import api

load_dotenv()

app = FastAPI()

# Wide open for a prototype running on localhost. Tighten allow_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/token")
def get_token(room: str = Query(...), identity: str = Query(...)):
    token = (
        api.AccessToken()
        .with_identity(identity)
        .with_name(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .to_jwt()
    )
    return {"token": token, "url": os.environ["LIVEKIT_URL"]}