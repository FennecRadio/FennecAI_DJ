# fennec_ai_dj/gpt_command_interpreter.py
"""
Free-form → JSON intent interpreter for Fennec AI DJ
• Uses GPT-3.5-turbo with a rich system prompt + few-shot examples
• Maps natural language (sad, faster, more acoustic, popular, spanish …)
  onto numeric audio-feature filters understood by the back-end.
• Logs the interpreted object to the server console:  🧠 interpreted: {...}
2025-04-23
"""
from __future__ import annotations
import os, json
from typing import Dict
from openai import OpenAI
from dotenv import load_dotenv

# ─── Init OpenAI client ──────────────────────────────────────────────────────
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─── Prompts ────────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """
You are an intent-parser for an AI DJ.

Return ONE JSON object *only* – no text around it.
See examples.

Shape:
{
  "intent": "recommend" | "control",
  "filters": [  // only for "recommend"
    {"feature":"valence","op":"<","value":0.3},
    {"feature":"energy", "op":">","value":0.7},
    ...
  ],
  "limit": 20  // optional, default 20
}

Lexical → feature mapping:
sad / sadder / depressing          → valence < 0.3
happy / uplifting                   → valence > 0.7
dark / gloomy                       → valence < 0.2
chill / relaxed / tired             → energy  < 0.4
energetic / hype / dance            → energy  > 0.7
slow(er)                            → tempo   < 90
fast(er) / high bpm                 → tempo   >130
acoustic                            → acousticness >0.5
instrumental                        → instrumentalness >0.5
loud                                → energy >0.8
quiet / softer                      → energy <0.3
famous / popular                    → popularity >70
underground / obscure               → popularity <40

Comparatives like "more sad" or "slightly faster" map to the same thresholds.

If a language is mentioned ("spanish track"), add:
  {"feature":"language","op":"=","value":"spanish"}

Control actions:
  skip, pause, resume, volume (needs direction up|down + amount 0-1)

If the user text is meaningless, respond with
  {"intent":"control","action":"noop"}.

Return ONLY valid JSON.
"""

_FEW_SHOTS = [
    ("play a sad song",
     {"intent":"recommend",
      "filters":[{"feature":"valence","op":"<","value":0.3}]}),

    ("make it happier!",
     {"intent":"recommend",
      "filters":[{"feature":"valence","op":">","value":0.7}]}),

    ("something acoustic and calm",
     {"intent":"recommend",
      "filters":[
         {"feature":"acousticness","op":">","value":0.5},
         {"feature":"energy","op":"<","value":0.4}
      ]}),

    ("faster track please",
     {"intent":"recommend",
      "filters":[{"feature":"tempo","op":">","value":130}]}),

    ("more energetic but instrumental",
     {"intent":"recommend",
      "filters":[
        {"feature":"energy","op":">","value":0.7},
        {"feature":"instrumentalness","op":">","value":0.5}
      ]}),

    ("play me something famous",
     {"intent":"recommend",
      "filters":[{"feature":"popularity","op":">","value":70}]}),

    ("an obscure chill tune",
     {"intent":"recommend",
      "filters":[
        {"feature":"popularity","op":"<","value":40},
        {"feature":"energy","op":"<","value":0.4}
      ]}),

    ("spanish upbeat song",
     {"intent":"recommend",
      "filters":[
        {"feature":"language","op":"=","value":"spanish"},
        {"feature":"energy","op":">","value":0.6}
      ]}),

    ("skip",   {"intent":"control","action":"skip"}),
    ("pause",  {"intent":"control","action":"pause"}),
    ("resume", {"intent":"control","action":"resume"}),
    ("volume up", {"intent":"control","action":"volume","direction":"up","amount":0.1})
]

# ─── Core function ──────────────────────────────────────────────────────────
def interpret_command(user_text: str) -> Dict:
    """
    Convert user_text into a JSON-able dict as defined above.
    Falls back to a 'noop' control if parsing fails.
    """
    # Assemble conversation with few-shot examples
    messages = [{"role":"system","content":_SYSTEM_PROMPT}]
    for q, ans in _FEW_SHOTS:
        messages.append({"role":"user","content":q})
        messages.append({"role":"assistant","content":json.dumps(ans, ensure_ascii=False)})

    messages.append({"role":"user","content":user_text})

    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo-0125",
            messages=messages,
            temperature=0.15,
            max_tokens=160
        )
        content = resp.choices[0].message.content.strip()
        obj = json.loads(content)
        # sanity minimal check
        if "intent" not in obj:
            raise ValueError("no intent field")
        print("🧠 interpreted:", obj)    #  ← appears in server console
        return obj

    except Exception as e:
        print("❌ interpreter error:", e)
        return {"intent":"control","action":"noop"}
