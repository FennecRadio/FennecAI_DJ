# fennec_ai_dj/local_ml/local_song_recommender.py
"""
Local recommender – now supports the advanced FILTER DSL.

Key change: recommend_by_filters(rules) understands:
   {"feature":"tempo","op":">","value":130}
   {"feature":"genre","op":"match","value":"hip hop"}
"""
from __future__ import annotations
import os, random, re, copy
import pandas as pd, joblib, math

BASE_DIR    = os.path.dirname(__file__)
DATA_PATH   = os.path.join(BASE_DIR, "cleaned_tracks.csv")
SCALER_PATH = os.path.join(BASE_DIR, "scaler.pkl")
KMEANS_PATH = os.path.join(BASE_DIR, "kmeans_model.pkl")

df     = pd.read_csv(DATA_PATH)
scaler = joblib.load(SCALER_PATH)
kmeans = joblib.load(KMEANS_PATH)

STANDARD_FEATURES = {
    "tempo","danceability","energy","valence","acousticness",
    "instrumentalness","speechiness","liveness","loudness",
    "popularity","duration_ms"
}
_SCALE_1K = {"danceability","energy","valence","acousticness",
             "speechiness","liveness"}

# ─── formatter ───────────────────────────────────────────────────────────────
def _fmt(sub: pd.DataFrame, limit:int) -> list[dict]:
    sample = sub.sample(min(limit,len(sub)))
    return [{
      "id":r["id"],
      "name":r["name"],
      "artists":[{"name":r["artists"]}],
      "album":{"name":r.get("album","Unknown"),
               "images":[{"url":r.get("image_url","")}]},
      "uri":f"spotify:track:{r['id']}"
    } for _,r in sample.iterrows()]

# ─── generic filter recommender ───────────────────────────────────────────────
def recommend_by_filters(rules:list[dict], limit:int=20) -> list[dict]:
    """
    rules: list of dicts with feature, op (>,>=,<,<=,==,match), value.
    Supports progressive relaxation like before.
    """
    if not rules: return []

    working = df
    for rule in rules:
        feature = rule.get("feature")
        op      = rule.get("op")
        value   = rule.get("value")

        # special "genre match" using regex on artist or track name
        if feature == "genre" and op == "match" and isinstance(value,str):
            pat = re.escape(value.lower())
            working = working[
               working["artists"].str.contains(pat, flags=re.I, na=False) |
               working["name"].str.contains(pat, flags=re.I, na=False)
            ]
            continue

        if feature not in STANDARD_FEATURES:
            continue  # unknown feature ignored

        val = float(value)
        if feature in _SCALE_1K and val > 0.01:
            val *= 0.001

        if   op == ">":  working = working[working[feature] >  val]
        elif op == ">=": working = working[working[feature] >= val]
        elif op == "<":  working = working[working[feature] <  val]
        elif op == "<=": working = working[working[feature] <= val]
        elif op == "==": working = working[working[feature] == val]

    if not working.empty:
        return _fmt(working, limit)

    # progressive relaxation: widen numeric thresholds ±25 % until hit
    relax_rules = copy.deepcopy(rules)
    for step in (0.25, 0.50, 0.75):
        sub = df
        for rule in relax_rules:
            feature, op, value = rule.get("feature"), rule.get("op"), rule.get("value")
            if feature == "genre": continue
            val = float(value)
            if feature in _SCALE_1K and val > 0.01:
                val *= 0.001
            if op in (">",">="):  val *= (1-step)   # lower threshold
            elif op in ("<","<="): val *= (1+step)  # raise threshold
            # apply
            if   op == ">":  sub = sub[sub[feature] >  val]
            elif op == ">=": sub = sub[sub[feature] >= val]
            elif op == "<":  sub = sub[sub[feature] <  val]
            elif op == "<=": sub = sub[sub[feature] <= val]
        if not sub.empty:
            return _fmt(sub, limit)

    # final fallback – random energetic mood
    moods = ["energetic","happy","calm","sad","dark"]
    return recommend_by_mood(random.choice(moods), limit)

# ─── other specific recommenders (unchanged) ─────────────────────────────────
def recommend_by_mood(mood:str,count:int=20):
    mapping={"happy":0,"sad":1,"energetic":2,"calm":3,"dark":4}
    sub=df[df["mood_cluster"]==mapping.get(mood.lower(),2)]
    return _fmt(sub,count) if not sub.empty else []

def recommend_by_tempo(speed:str,count:int=20):
    speed=speed.lower()
    if speed=="fast":   sub=df[df["tempo"]>130]
    elif speed=="slow": sub=df[df["tempo"]<90]
    else:               sub=df[(df["tempo"]>=90)&(df["tempo"]<=130)]
    return _fmt(sub,count) if not sub.empty else []

def recommend_by_genre(keyword:str,count:int=20):
    kw=keyword.lower().strip()
    if kw=="instrumental": sub=df[df["instrumentalness"]>0.8]
    else:
        pat=re.escape(kw)
        sub=df[df["artists"].str.contains(pat,flags=re.I,na=False)|
               df["name"].str.contains(pat,flags=re.I,na=False)]
    return _fmt(sub,count) if not sub.empty else []

def recommend_by_user_profile(profile:dict,count:int=20):
    vec=pd.DataFrame([profile])[["danceability","energy","valence","acousticness","tempo"]]
    cl=kmeans.predict(scaler.transform(vec))[0]
    sub=df[df["mood_cluster"]==cl]
    return _fmt(sub,count) if not sub.empty else []

def get_recommendations_from_local_model(count:int=20):
    return recommend_by_mood(random.choice(["happy","sad","energetic","calm","dark"]),count)
