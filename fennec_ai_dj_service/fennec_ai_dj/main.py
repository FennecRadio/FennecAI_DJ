# fennec_ai_dj/main.py
"""
Fennec AI DJ back‑end
2025‑04‑22 • integrate top‑track seeds (weight +2) without deleting anything
"""
from fastapi.responses import RedirectResponse
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional 
import logging

from fennec_ai_dj.spotify_api import (
    get_spotify_auth_url, get_access_token, get_current_spotify_user_id,
    get_user_saved_track_ids, get_user_recent_track_ids,
    get_user_top_track_ids,                     # NEW
    get_tracks_metadata 
)
from fennec_ai_dj.local_ml.local_song_recommender import (
    get_recommendations_from_local_model, recommend_by_user_profile,
    recommend_by_filters, df as local_df,
)
from fennec_ai_dj.user_feedback_store import (
    store_feedback, get_liked_songs, get_disliked_songs
)
from fennec_ai_dj.gpt_command_interpreter import interpret_command

app = FastAPI()
logger = logging.getLogger("uvicorn.error")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ─── Schemas ─────────────────────────────────────────────────────────────────
class Feedback(BaseModel):
    user_id:str; track_id:str; feedback:str
class Command(BaseModel):
    user_id:str; message:str; access_token: Optional[str] = None 

# ─── Feature columns & weights ───────────────────────────────────────────────
AUDIO_COLS = ["danceability","energy","valence","acousticness","tempo"]
WEIGHTS = {
    "spotify": 1,   # saved + recent
    "top":     2,   # ★ new
    "like":    3,
    "dislike": -3
}

# ─── Helpers ────────────────────────────────────────────────────────────────
def _weighted_profile(df):
    if df.empty or df["w"].sum()==0: return None
    return {c:(df[c]*df["w"]).sum()/df["w"].sum() for c in AUDIO_COLS}


def _drop_bad(lst,bad): return [t for t in lst if t["id"] not in bad]
def _strip_disliked(recs, bad_ids):
    return [t for t in recs if t["id"] not in bad_ids]


# ★ helper to patch missing album/image
def _enrich(recs:list[dict], access_token:str|None):
    if not access_token: 
        return recs

    # gather IDs that need enrichment
    need=[t["id"] for t in recs
          if t["album"]["name"]=="Unknown" or not t["album"]["images"][0]["url"]]
    meta_map=get_tracks_metadata(need[:50], access_token)   # one call

    for t in recs:
        meta=meta_map.get(t["id"])
        if not meta: 
            continue
        if meta.get("album_name"):
            t["album"]["name"]=meta["album_name"]
        if meta.get("image_url"):
            t["album"]["images"][0]["url"]=meta["image_url"]
    return recs



# ─── Auth endpoints (unchanged) ─────────────────────────────────────────────
@app.get("/login")
def login(): return {"url": get_spotify_auth_url()}

@app.get("/callback")
def callback(code:str):
    tok=get_access_token(code)
    uid=get_current_spotify_user_id(tok["access_token"])
    return RedirectResponse(
        f"http://localhost:5501/?access_token={tok['access_token']}&user_id={uid}"
    )

# ─── Feedback persistence (unchanged) ───────────────────────────────────────
@app.post("/feedback")
def feedback(fb:Feedback):
    if fb.feedback not in {"like","dislike"}:
        raise HTTPException(400,"feedback must be like|dislike")
    store_feedback(fb.user_id, fb.track_id, fb.feedback)
    return {"msg":"ok"}

# ─── recommendation endpoint (adds enrich) ──────────────────────────────────
@app.get("/recommendations")
def recommendations(access_token:str=Query(...),user_id:str=Query(...)):
    dislikes=set(get_disliked_songs(user_id))
    likes=set(get_liked_songs(user_id))

    saved_recent=[]; top=[]
    try:
        saved_recent=list(dict.fromkeys(
            get_user_saved_track_ids(access_token,25)+
            get_user_recent_track_ids(access_token,25)
        ))
    except Exception as e: logger.warning("saved/recent: %s",e)
    try:
        top=get_user_top_track_ids(access_token,20)
    except Exception as e: logger.warning("top-tracks: %s",e)

    id2w=({tid:WEIGHTS["spotify"] for tid in saved_recent}|
          {tid:WEIGHTS["top"]     for tid in top}|
          {tid:WEIGHTS["like"]    for tid in likes}|
          {tid:WEIGHTS["dislike"] for tid in dislikes})
    if not id2w:
        recs=_enrich(get_recommendations_from_local_model(),access_token)
        return {"recommendations":_strip_disliked(recs,dislikes)}

    subset=local_df[local_df["id"].isin(id2w)].copy()
    subset["w"]=subset["id"].map(id2w).fillna(0)
    prof=_weighted_profile(subset)
    recs=(recommend_by_user_profile(prof) if prof
          else get_recommendations_from_local_model())
    recs=_enrich(recs, access_token)
    return {"recommendations":_strip_disliked(recs,dislikes)}

# fennec_ai_dj/main.py   (only /command endpoint changed)

# … all imports & earlier code unchanged …

@app.post("/command")
def command(cmd:Command):
    obj=interpret_command(cmd.message)
    logger.info("🧠 interpreted: %s", obj)          # log to server
    if obj.get("intent")=="control":
        return obj
    if obj.get("intent")=="recommend":
        bad=set(get_disliked_songs(cmd.user_id))
        recs=recommend_by_filters(obj.get("filters",[]), obj.get("limit",20))
        recs=_enrich(recs, cmd.access_token)
        return {"recommendations":_strip_disliked(recs,bad)}
    raise HTTPException(400,"unknown intent")

