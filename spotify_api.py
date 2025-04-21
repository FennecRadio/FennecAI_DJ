# fennec_ai_dj/spotify_api.py

import os
import requests
import base64
from dotenv import load_dotenv
from fastapi import HTTPException

# Load environment variables
load_dotenv()

SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI")

if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET or not SPOTIFY_REDIRECT_URI:
    raise ValueError("Spotify API credentials are missing! Check your .env file.")

def get_spotify_auth_url():
    """Authorization URL for user login + required scopes."""
    scopes = [
        "streaming",
        "user-read-email",
        "user-read-private",
        "user-read-playback-state",
        "user-modify-playback-state",
        "user-read-currently-playing",
        "user-library-read",           # to read Saved Tracks
        "user-read-recently-played"    # to read Recently Played
    ]
    scope_str = " ".join(scopes)
    return (
        "https://accounts.spotify.com/authorize"
        f"?response_type=code"
        f"&client_id={SPOTIFY_CLIENT_ID}"
        f"&scope={scope_str}"
        f"&redirect_uri={SPOTIFY_REDIRECT_URI}"
    )

def get_access_token(auth_code: str) -> dict:
    """Exchange auth code for access & refresh tokens."""
    token_url = "https://accounts.spotify.com/api/token"
    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type":    "authorization_code",
        "code":          auth_code,
        "redirect_uri":  SPOTIFY_REDIRECT_URI
    }
    resp = requests.post(token_url, headers=headers, data=data)
    return resp.json()

def get_current_spotify_user_id(access_token: str) -> str:
    """Fetch the Spotify user’s own account ID (/me)."""
    url = "https://api.spotify.com/v1/me"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json().get("id")

def get_user_saved_track_ids(access_token: str, limit: int = 20) -> list[str]:
    """
    Get the user’s “Your Library → Saved Tracks” IDs.
    Requires scope: user-library-read
    """
    url = "https://api.spotify.com/v1/me/tracks"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": limit}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return [item["track"]["id"] for item in resp.json().get("items", []) if item.get("track")]

def get_user_recent_track_ids(access_token: str, limit: int = 20) -> list[str]:
    """
    Get the user’s Recently Played track IDs.
    Requires scope: user-read-recently-played
    """
    url = "https://api.spotify.com/v1/me/player/recently-played"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": limit}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return [item["track"]["id"] for item in resp.json().get("items", []) if item.get("track")]

# Legacy / optional endpoints below — your hybrid logic will now use the seed‑fetchers above
def get_recently_played_tracks(access_token: str) -> list[dict]:
    """Full track objects from recently-played (pre‑feature‑lookup)."""
    url = "https://api.spotify.com/v1/me/player/recently-played"
    headers = {"Authorization": f"Bearer {access_token.strip()}"}
    params = {"limit": 20}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    items = resp.json().get("items", [])
    tracks = []
    for item in items:
        track = item.get("track") or {}
        album = track.get("album", {})
        image = album.get("images", [{}])[0].get("url", "")
        tracks.append({
            "id":         track.get("id"),
            "name":       track.get("name"),
            "artist":     track.get("artists", [{}])[0].get("name", ""),
            "album":      album.get("name", ""),
            "popularity": track.get("popularity", 0),
            "image":      image
        })
    return tracks

def get_audio_features(track_ids: list[str], access_token: str) -> list[dict]:
    """Batch‑fetch audio features — now mostly unused in hybrid mode."""
    url = "https://api.spotify.com/v1/audio-features"
    headers = {"Authorization": f"Bearer {access_token.strip()}"}
    unique_ids = list(set(track_ids))[:100]
    params = {"ids": ",".join(unique_ids)}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        return []
    return resp.json().get("audio_features", [])

def get_recently_played_tracks_with_features(access_token: str) -> list[dict]:
    """Helper that stitches together get_recently_played_tracks + get_audio_features."""
    tracks = get_recently_played_tracks(access_token)
    ids    = [t["id"] for t in tracks if t.get("id")]
    feats  = get_audio_features(ids, access_token)
    enriched = []
    for t, f in zip(tracks, feats):
        if f and f.get("id") == t["id"]:
            t.update({
                "danceability":  f.get("danceability"),
                "energy":        f.get("energy"),
                "tempo":         f.get("tempo"),
                "valence":       f.get("valence"),
                "acousticness":  f.get("acousticness")
            })
            enriched.append(t)
    return enriched
