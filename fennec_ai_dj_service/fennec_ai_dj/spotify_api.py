# fennec_ai_dj/spotify_api.py
"""
Spotify REST helpers
2025‑04‑22 • + user‑top‑read scope & get_user_top_track_ids()
"""
import os, base64, requests
from dotenv import load_dotenv
from fastapi import HTTPException

# ─── ENV ─────────────────────────────────────────────────────────────────────
load_dotenv()
SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI")
if not all([SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI]):
    raise ValueError("Spotify API credentials missing!")

# ─── AUTH URL ────────────────────────────────────────────────────────────────
def get_spotify_auth_url() -> str:
    scopes = [
        "streaming", "user-read-email", "user-read-private",
        "user-read-playback-state", "user-modify-playback-state",
        "user-read-currently-playing",
        "user-library-read",          # Saved tracks
        "user-read-recently-played",  # Recently played
        "user-top-read"               # ★ NEW – top artists / tracks
    ]
    return (
        "https://accounts.spotify.com/authorize"
        f"?response_type=code"
        f"&client_id={SPOTIFY_CLIENT_ID}"
        f"&scope={' '.join(scopes)}"
        f"&redirect_uri={SPOTIFY_REDIRECT_URI}"
    )

# ─── TOKEN EXCHANGE ──────────────────────────────────────────────────────────
def get_access_token(code:str)->dict:
    auth = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type":  "application/x-www-form-urlencoded"
        },
        data={
            "grant_type":"authorization_code",
            "code":code,
            "redirect_uri":SPOTIFY_REDIRECT_URI
        }
    )
    return r.json()

# ─── BASIC HELPERS ───────────────────────────────────────────────────────────
def _hdr(tok): return {"Authorization": f"Bearer {tok}"}

def get_current_spotify_user_id(tok:str) -> str:
    r = requests.get("https://api.spotify.com/v1/me", headers=_hdr(tok))
    if r.status_code!=200: raise HTTPException(r.status_code,r.text)
    return r.json().get("id")

# ─── SEED COLLECTORS ─────────────────────────────────────────────────────────
def get_user_saved_track_ids(tok:str, limit:int=20)->list[str]:
    r = requests.get("https://api.spotify.com/v1/me/tracks",
                     headers=_hdr(tok), params={"limit":limit})
    if r.status_code!=200: raise HTTPException(r.status_code,r.text)
    return [i["track"]["id"] for i in r.json().get("items",[]) if i.get("track")]

def get_user_recent_track_ids(tok:str, limit:int=20)->list[str]:
    r = requests.get("https://api.spotify.com/v1/me/player/recently-played",
                     headers=_hdr(tok), params={"limit":limit})
    if r.status_code!=200: raise HTTPException(r.status_code,r.text)
    return [i["track"]["id"] for i in r.json().get("items",[]) if i.get("track")]

# ★ NEW – top tracks
def get_user_top_track_ids(tok:str, limit:int=20, time_range:str="medium_term")->list[str]:
    """
    time_range: short_term (4 weeks), medium_term (6 m, default), long_term (years)
    """
    r = requests.get(
        "https://api.spotify.com/v1/me/top/tracks",
        headers=_hdr(tok),
        params={"limit":limit, "time_range":time_range}
    )
    if r.status_code!=200: raise HTTPException(r.status_code,r.text)
    return [t["id"] for t in r.json().get("items",[])]

# ─── LEGACY / FEATURE LOOKUP (unchanged) ─────────────────────────────────────
def get_recently_played_tracks(tok:str)->list[dict]:
    url = "https://api.spotify.com/v1/me/player/recently-played"
    r   = requests.get(url, headers=_hdr(tok), params={"limit":20})
    if r.status_code!=200: raise HTTPException(r.status_code,r.text)
    tracks=[]
    for item in r.json().get("items",[]):
        track=item.get("track") or {}
        album=track.get("album",{})
        image=album.get("images",[{}])[0].get("url","")
        tracks.append({
            "id":track.get("id"),
            "name":track.get("name"),
            "artist":track.get("artists",[{}])[0].get("name",""),
            "album":album.get("name",""),
            "popularity":track.get("popularity",0),
            "image":image
        })
    return tracks

def get_audio_features(ids:list[str], tok:str)->list[dict]:
    if not ids: return []
    url="https://api.spotify.com/v1/audio-features"
    r=requests.get(url, headers=_hdr(tok),
                   params={"ids":",".join(list(dict.fromkeys(ids))[:100])})
    return r.json().get("audio_features",[]) if r.status_code==200 else []

def get_recently_played_tracks_with_features(tok:str)->list[dict]:
    tracks=get_recently_played_tracks(tok)
    features=get_audio_features([t["id"] for t in tracks if t.get("id")], tok)
    enriched=[]
    for t,f in zip(tracks,features):
        if f and f.get("id")==t["id"]:
            t.update({k:f.get(k) for k in
                     ("danceability","energy","tempo","valence","acousticness")})
            enriched.append(t)
    return enriched

def get_track_metadata(track_id:str, access_token:str)->dict:
    """
    Return {"album_name":str, "image_url":str} for a track id.
    If API fails, returns {}.
    """
    url=f"https://api.spotify.com/v1/tracks/{track_id}"
    r=requests.get(url, headers={"Authorization":f"Bearer {access_token}"})
    if r.status_code!=200:
        return {}
    data=r.json()
    album=data.get("album",{})
    images=album.get("images",[])
    return {
        "album_name": album.get("name","Unknown"),
        "image_url" : images[0]["url"] if images else ""
    }

_meta_cache: dict[str, dict] = {} 

def get_tracks_metadata(ids:list[str], access_token:str) -> dict[str,dict]:
    """
    Batch‑fetch up to 50 track objects and return a mapping:
       id → {"album_name": str, "image_url": str}
    Uses an in‑process LRU cache so subsequent calls for the same IDs are free.
    """
    if not ids: return {}
    # check cache first
    out={tid:_meta_cache[tid] for tid in ids if tid in _meta_cache}
    missing=[tid for tid in ids if tid not in _meta_cache]
    if not missing:
        return out

    # Spotify batch endpoint (max 50)
    url="https://api.spotify.com/v1/tracks"
    r=requests.get(url, headers=_hdr(access_token),
                   params={"ids":",".join(missing)})
    if r.status_code!=200:
        return out  # return whatever we already have

    for obj in r.json().get("tracks",[]):
        if not obj: continue
        album=obj.get("album",{})
        images=album.get("images",[])
        meta={
            "album_name": album.get("name","Unknown"),
            "image_url":  images[0]["url"] if images else ""
        }
        _meta_cache[obj["id"]]=meta
        out[obj["id"]]=meta
    return out
