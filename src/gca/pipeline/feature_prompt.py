SYSTEM = """\
You are a game market analyst. Given a game's title, description, and player reviews,
extract structured metadata. Return ONLY valid JSON matching the schema below — no prose.
""".strip()

USER_TEMPLATE = """\
Title: {title}

Description:
{description}

Sample player reviews:
{reviews}

Canary question: Is this a video game (not a utility or non-game app)?
Answer exactly 'yes' or 'no' in the _canary_answer field.

Return a JSON object with these exact fields:
{{
  "genre": "<primary genre, e.g. RPG / Action / Strategy / Puzzle / Sports>",
  "subgenre": "<more specific subgenre, e.g. Roguelite / Tower Defense / Battle Royale>",
  "bm_dist": {{
    "gacha": <0.0-1.0>,
    "ads": <0.0-1.0>,
    "premium": <0.0-1.0>,
    "sub": <0.0-1.0>
  }},
  "play_style": ["<e.g. competitive>", "<casual>", "<co-op>"],
  "session_length_minutes": <typical session length as a float>,
  "core_loop": "<1-2 sentence description of the core gameplay loop>",
  "_canary_answer": "yes"
}}

Rules:
- bm_dist values must sum to 1.0
- session_length_minutes must be a positive number
- play_style must be a non-empty list
- Output only the JSON object, nothing else
"""
