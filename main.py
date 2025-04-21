# fennec_ai_dj/main.py
"""
FastAPI back‑end for Fennec AI DJ.

Key changes
───────────
1. /command now expects the *JSON* object produced by gpt_command_interpreter
   and routes to the proper local recommender:
      • play_mood    → recommend_by_mood
      • play_tempo   → recommend_by_tempo   (NEW)
      • play_genre   → recommend_by_genre   (NEW)
2. Non‑recommendation intents (skip / pause / resume / volume / describe) are
   echoed back as {"action": "<intent>", ...} so the front‑end can react later
   if desired.
"""

from fastapi.responses import RedirectResponse
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

from fennec_ai_dj.spotify_api import (
    get_spotify_auth_url,
    get_access_token,
    get_current_spotify_user_id,
    get_user_saved_track_ids,
    get_user_recent_track_ids,
)
from fennec_ai_dj.local_ml.local_song_recommender import (
    get_recommendations_from_local_model,
    recommend_by_user_profile,
    recommend_by_mood,
    recommend_by_tempo,          # NEW
    recommend_by_genre,          # NEW
    df as local_df,
)
from fennec_ai_dj.user_feedback_store import (
    store_feedback,
    get_liked_songs,
)
from fennec_ai_dj.gpt_command_interpreter import interpret_command

app = FastAPI()
logger = logging.getLogger("uvicorn.error")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Request Models ───────────────────────────────────────────────────────────
class FeedbackRequest(BaseModel):
    user_id: str
    track_id: str
    feedback: str  # "like" or "dislike"

class CommandRequest(BaseModel):
    user_id: str
    message: str

# ─── Routes ───────────────────────────────────────────────────────────────────
@app.get("/")
def read_root():
    return {"message": "Fennec AI DJ is alive 🎧"}

@app.get("/login")
def login():
    return {"url": get_spotify_auth_url()}

@app.get("/callback")
def callback(code: str):
    token_data = get_access_token(code)
    if not token_data or "access_token" not in token_data:
        raise HTTPException(400, "Invalid authorization code")

    access_token = token_data["access_token"]
    user_id = get_current_spotify_user_id(access_token)

    redirect_url = (
        f"http://localhost:5501/"
        f"?access_token={access_token}"
        f"&user_id={user_id}"
    )
    return RedirectResponse(redirect_url)

@app.get("/recommendations")
def recommendations(
    access_token: str = Query(...),
    user_id:      str = Query(...)
):
    """
    Hybrid recommendations (unchanged from previous version).
    """
    # 1️⃣ Spotify‑seeded profile
    try:
        saved_ids  = get_user_saved_track_ids(access_token, limit=20)
        recent_ids = get_user_recent_track_ids(access_token, limit=20)
        seeds = list(dict.fromkeys(saved_ids + recent_ids))
        seed_df = local_df[local_df["id"].isin(seeds)]
        if not seed_df.empty:
            profile = {k: seed_df[k].mean() for k in
                       ["danceability","energy","valence","acousticness","tempo"]}
            return {"recommendations": recommend_by_user_profile(profile)}
    except Exception as e:
        logger.exception("Spotify‑seed seed failed: %s", e)

    # 2️⃣ App “Like” seeds
    liked = get_liked_songs(user_id)
    if liked:
        seed_df = local_df[local_df["id"].isin(liked)]
        if not seed_df.empty:
            profile = {k: seed_df[k].mean() for k in
                       ["danceability","energy","valence","acousticness","tempo"]}
            return {"recommendations": recommend_by_user_profile(profile)}

    # 3️⃣ Fallback
    return {"recommendations": get_recommendations_from_local_model()}

@app.post("/feedback")
def feedback(payload: FeedbackRequest):
    if payload.feedback not in ("like", "dislike"):
        raise HTTPException(400, "Feedback must be 'like' or 'dislike'")
    store_feedback(payload.user_id, payload.track_id, payload.feedback)
    return {"message": f"✅ {payload.feedback.capitalize()} received"}

# ──────────────────────────────────────────────────────────────────────────────
#  GPT COMMAND ENDPOINT  – THIS IS THE BIG FIX
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/command")
def command(cmd: CommandRequest):
    """
    Chat commands powered by GPT. Always returns either
      • {"recommendations":[…]}   – for play_xxx intents
      • {"action": "..."}         – for control intents
    The front‑end keeps its simple logic: if it sees .recommendations,
    it plays the first track; otherwise it shows an info message.
    """
    intent_obj = interpret_command(cmd.message)
    intent     = intent_obj.get("intent")

    # — Recommendation intents —
    if intent == "play_mood":
        mood = intent_obj.get("mood", "calm")
        return {"recommendations": recommend_by_mood(mood)}

    if intent == "play_tempo":
        tempo = intent_obj.get("tempo", "medium")
        return {"recommendations": recommend_by_tempo(tempo)}

    if intent == "play_genre":
        genre = intent_obj.get("genre", "").strip()
        if not genre:
            raise HTTPException(400, "Genre missing in command")
        recs = recommend_by_genre(genre)
        if not recs:
            raise HTTPException(404, f"No tracks found for genre '{genre}'")
        return {"recommendations": recs}

    # — Control / info intents (skip / pause / volume / describe …) —
    if intent in {"skip","pause","resume","describe"}:
        return {"action": intent}

    if intent == "volume":
        return {
            "action":     "volume",
            "direction":  intent_obj.get("direction", "up"),
            "amount":     float(intent_obj.get("amount", 0.1))
        }

    raise HTTPException(400, f"Unsupported intent: {intent}")
