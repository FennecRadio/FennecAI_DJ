import random
from fennec_ai_dj.spotify_api import get_audio_features

def compute_user_profile(tracks):
    keys = ["danceability", "energy", "tempo", "valence", "acousticness"]
    profile = {k: 0.0 for k in keys}
    valid = [t for t in tracks if all(k in t for k in keys)]

    if not valid:
        return None

    for t in valid:
        for k in keys:
            profile[k] += t[k]
    for k in keys:
        profile[k] /= len(valid)
    return profile

def search_candidate_tracks(access_token, genre="pop"):
    import requests
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"q": f"genre:{genre}", "type": "track", "limit": 20}
    res = requests.get("https://api.spotify.com/v1/search", headers=headers, params=params)
    if res.status_code != 200:
        print("Search failed:", res.text)
        return []
    items = res.json().get("tracks", {}).get("items", [])
    return [{
        "id": t["id"],
        "name": t["name"],
        "artist": t["artists"][0]["name"],
        "album": t["album"]["name"],
        "image": t["album"]["images"][0]["url"] if t["album"].get("images") else ""
    } for t in items]

def score_candidates(user_profile, candidates, features):
    def dist(a, b):
        return sum((a[k] - b.get(k, 0.0))**2 for k in a) ** 0.5
    scored = [(t, dist(user_profile, f)) for t, f in zip(candidates, features) if f]
    scored.sort(key=lambda x: x[1])
    return [t for t, _ in scored]

def generate_recommendations(access_token, enriched_tracks):
    profile = compute_user_profile(enriched_tracks)
    if profile:
        candidates = search_candidate_tracks(access_token, genre="pop")
        if candidates:
            ids = [c["id"] for c in candidates]
            features = get_audio_features(ids, access_token)
            top = score_candidates(profile, candidates, features)[:5]
            return _reformat_for_frontend(top)
    return _reformat_for_frontend(random.sample(enriched_tracks, min(5, len(enriched_tracks))))

def _reformat_for_frontend(tracks):
    formatted = []
    for t in tracks:
        formatted.append({
            "id": t.get("id"),
            "name": t.get("name"),
            "artists": [{"name": t.get("artist", "Unknown")}],
            "album": {
                "name": t.get("album", "Unknown"),
                "images": [{"url": t.get("image", "")}]
            }
        })
    return formatted
