# fennec_ai_dj/user_feedback_store.py

import json
import os
from threading import Lock

# Path to persistent feedback store
FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), "user_feedback.json")
_lock = Lock()

# Ensure the file exists
if not os.path.exists(FEEDBACK_FILE):
    with open(FEEDBACK_FILE, "w") as f:
        json.dump({}, f)

# Load existing feedback (mapping user_id → { track_id: feedback })
try:
    with open(FEEDBACK_FILE, "r") as f:
        feedback_store = json.load(f)
except Exception as e:
    print("⚠️ Failed to load feedback file, starting fresh:", e)
    feedback_store = {}

def save_feedback():
    """Persist feedback_store to disk safely."""
    with _lock:
        try:
            with open(FEEDBACK_FILE, "w") as f:
                json.dump(feedback_store, f, indent=2)
            print("✅ Feedback written successfully.")
        except Exception as e:
            print("❌ Failed to write feedback file:", e)

def store_feedback(user_id: str, track_id: str, feedback: str):
    """
    Record a like/dislike for a given user.
    user_id: Spotify user ID (or 'guest')
    track_id: Spotify track ID
    feedback: 'like' or 'dislike'
    """
    if feedback not in {"like", "dislike"}:
        raise ValueError("Feedback must be 'like' or 'dislike'")
    with _lock:
        user_data = feedback_store.setdefault(user_id, {})
        user_data[track_id] = feedback
        feedback_store[user_id] = user_data
        print(f"📝 Storing feedback: user={user_id}, track={track_id}, feedback={feedback}")
        save_feedback()

def get_user_feedback(user_id: str) -> dict:
    """
    Retrieve all feedback entries for a user.
    Returns a dict mapping track_id → feedback.
    """
    return feedback_store.get(user_id, {}).copy()

def get_liked_songs(user_id: str) -> list[str]:
    """Return a list of track IDs the user has liked."""
    return [tid for tid, fb in feedback_store.get(user_id, {}).items() if fb == "like"]

def get_disliked_songs(user_id: str) -> list[str]:
    """Return a list of track IDs the user has disliked."""
    return [tid for tid, fb in feedback_store.get(user_id, {}).items() if fb == "dislike"]
