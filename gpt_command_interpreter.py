# fennec_ai_dj/gpt_command_interpreter.py

import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load .env for OPENAI_API_KEY
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def interpret_command(user_input: str) -> dict:
    """
    Parses a free‑form user input and classifies it into one of several intents:
      - play_mood:    {"intent":"play_mood",    "mood":"happy"}
      - play_genre:   {"intent":"play_genre",   "genre":"hip hop"}
      - play_tempo:   {"intent":"play_tempo",   "tempo":"fast"}
      - skip:         {"intent":"skip"}
      - volume:       {"intent":"volume",       "direction":"up"|"down", "amount":0.1}
      - describe:     {"intent":"describe"}
      - fallback to play_mood if nothing else matches
    """
    try:
        # Ask GPT to emit a JSON intent object
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a music‑DJ command parser. "
                        "User messages can ask to play a mood, a genre, skip, pause/resume, "
                        "adjust volume, or describe the current song. "
                        "Always respond with a single JSON object (no extra text) "
                        "with keys:\n"
                        "- intent: one of [play_mood, play_genre, play_tempo, skip, "
                        "pause, resume, volume, describe]\n"
                        "- For play_mood: include mood (happy, sad, energetic, calm, dark).\n"
                        "- For play_genre: include genre (e.g. 'hip hop').\n"
                        "- For play_tempo: include tempo ('fast', 'slow', 'medium').\n"
                        "- For skip, pause, resume, describe: no extra fields.\n"
                        "- For volume: include direction ('up' or 'down') and optional amount (0.0–1.0).\n"
                        "Examples:\n"
                        "`{\"intent\":\"play_mood\",\"mood\":\"energetic\"}`\n"
                        "`{\"intent\":\"skip\"}`\n"
                        "`{\"intent\":\"volume\",\"direction\":\"up\",\"amount\":0.1}`"
                    )
                },
                {"role": "user", "content": user_input}
            ],
            temperature=0
        )

        content = resp.choices[0].message.content.strip()
        intent_obj = json.loads(content)
        print(f"🧠 Parsed intent: {intent_obj}")
        return intent_obj

    except Exception as e:
        print("❌ GPT interpretation failed:", e)
        # fallback to a simple mood play
        return {"intent": "play_mood", "mood": "calm"}
