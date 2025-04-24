# fennec_ai_dj/local_ml/hybrid_recommender.py

import pandas as pd
from fennec_ai_dj.spotify_api import (
    get_user_saved_track_ids,
    get_user_recent_track_ids
)
from fennec_ai_dj.local_ml.local_song_recommender import (
    recommend_by_user_profile,
    get_recommendations_from_local_model
)

# Load the cleaned CSV once
CSV_PATH = "fennec_ai_dj/local_ml/cleaned_tracks.csv"
df = pd.read_csv(CSV_PATH).set_index("id")

def hybrid_recommendations(access_token: str, feedback_likes: list[dict]):
    # 1) Pull Spotify seeds
    saved_ids  = get_user_saved_track_ids(access_token, limit=20)
    recent_ids = get_user_recent_track_ids(access_token, limit=20)
    
    # 2) Pull in‑app liked IDs
    feedback_ids = [t["id"] for t in feedback_likes]
    
    # 3) Consolidate & dedupe
    all_ids = list(dict.fromkeys(saved_ids + recent_ids + feedback_ids))
    
    # 4) Lookup local features
    seeds = []
    for tid in all_ids:
        if tid in df.index:
            row = df.loc[tid]
            seeds.append({
                k: row[k]
                for k in ["danceability","energy","valence","acousticness","tempo"]
            })
    # 5) Build profile & recommend
    if seeds:
        # average features into one profile
        profile = {k: sum(d[k] for d in seeds)/len(seeds) for k in seeds[0]}
        return recommend_by_user_profile(profile)
    
    # 6) Fallback
    return get_recommendations_from_local_model()
