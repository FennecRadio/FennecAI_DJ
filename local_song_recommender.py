# fennec_ai_dj/local_ml/local_song_recommender.py
"""
Local (offline) recommendation helpers for Fennec AI DJ.

New in this version
───────────────────
• recommend_by_tempo("fast" | "medium" | "slow")
• recommend_by_genre("hip hop" | "rock" | "instrumental" …)

Both reuse the cleaned_tracks.csv that already ships with the project.
"""

from __future__ import annotations
import os, random, re
import pandas as pd, joblib

# ─── Fixed paths ──────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(__file__)
DATA_PATH   = os.path.join(BASE_DIR, "cleaned_tracks.csv")
SCALER_PATH = os.path.join(BASE_DIR, "scaler.pkl")
KMEANS_PATH = os.path.join(BASE_DIR, "kmeans_model.pkl")

# ─── Load models & data (once at import‑time) ─────────────────────────────────
df     = pd.read_csv(DATA_PATH)
scaler = joblib.load(SCALER_PATH)
kmeans = joblib.load(KMEANS_PATH)

FEATURE_COLUMNS = ["danceability", "energy", "valence",
                   "acousticness", "tempo"]

# ensure we have the columns we need
df = df.dropna(subset=FEATURE_COLUMNS + ["mood_cluster"]).reset_index(drop=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def _format_for_frontend(tracks_df: pd.DataFrame) -> list[dict]:
    """Map a DataFrame slice into the minimal structure the Web SDK expects."""
    formatted: list[dict] = []
    for _, row in tracks_df.iterrows():
        formatted.append({
            "id":      row["id"],
            "name":    row["name"],
            "artists": [{"name": row["artists"]}],
            "album": {
                "name":   row.get("album", "Unknown Album"),
                "images": [{"url": row.get("image_url", "")}]
            },
            "uri": f"spotify:track:{row['id']}"
        })
    return formatted


# ─── Mood‑cluster recommendation (unchanged) ──────────────────────────────────
def recommend_by_mood(mood_label: str, count: int = 20) -> list[dict]:
    mapping = {"happy": 0, "sad": 1, "energetic": 2,
               "calm": 3, "dark": 4}
    cluster = mapping.get(mood_label.lower())
    if cluster is None:
        return []
    sample = df[df["mood_cluster"] == cluster]
    if sample.empty:
        return []
    return _format_for_frontend(sample.sample(min(count, len(sample))))


# ─── NEW #1: Tempo‑based recommendation ───────────────────────────────────────
def recommend_by_tempo(speed: str, count: int = 20) -> list[dict]:
    """
    speed ∈ {'fast','medium','slow'}
      fast   → tempo > 130 BPM
      medium → 90–130 BPM
      slow   → tempo < 90 BPM
    """
    speed = speed.lower()
    if speed == "fast":
        subset = df[df["tempo"] > 130]
    elif speed == "slow":
        subset = df[df["tempo"] < 90]
    else:  # medium + fallback
        subset = df[(df["tempo"] >= 90) & (df["tempo"] <= 130)]

    if subset.empty:
        return []
    return _format_for_frontend(subset.sample(min(count, len(subset))))


# ─── NEW #2: Genre / “instrumental” recommendation ────────────────────────────
def recommend_by_genre(keyword: str, count: int = 20) -> list[dict]:
    """
    Very lightweight genre filter:
    • matches the keyword inside the artists or track name (case‑insensitive)
    • special keyword 'instrumental' uses instrumentalness > 0.8
    """
    kw = keyword.lower().strip()
    if kw == "instrumental":
        subset = df[df["instrumentalness"] > 0.8]
    else:
        pattern = re.escape(kw)
        subset  = df[
            df["artists"].str.contains(pattern, flags=re.I, na=False) |
            df["name"].str.contains(pattern, flags=re.I, na=False)
        ]

    if subset.empty:
        return []
    return _format_for_frontend(subset.sample(min(count, len(subset))))


# ─── Profile‑based recommendation (unchanged) ─────────────────────────────────
def recommend_by_user_profile(profile: dict, count: int = 20) -> list[dict]:
    inp_df      = pd.DataFrame([profile])[FEATURE_COLUMNS]
    cluster     = kmeans.predict(scaler.transform(inp_df))[0]
    subset      = df[df["mood_cluster"] == cluster]
    if subset.empty:
        return []
    return _format_for_frontend(subset.sample(min(count, len(subset))))


# ─── Random fallback ──────────────────────────────────────────────────────────
def get_recommendations_from_local_model(count: int = 20) -> list[dict]:
    return recommend_by_mood(random.choice(["happy","sad","energetic","calm","dark"]),
                             count=count)
