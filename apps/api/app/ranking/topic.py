"""
Topic detection from text evidence: the license record's category, title,
filename, origin-URL slug, yt-dlp tags/description, and moment labels.

Deliberately simple and explainable, and it says when it doesn't know. The
@rankzilla23 inventory shows why: 242 of 295 titles are the identical "DON'T
CHECK THE SOUND 😭😭", which carries no topic at all. Unknown topics go to a
human in the clip browser; they are never guessed.
"""
from __future__ import annotations

import re

from .db import CATEGORIES

KEYWORDS = {
    "animals": ["dog", "puppy", "cat", "kitten", "goat", "lamb", "sheep", "duck", "goose",
                "chicken", "rooster", "hen", "horse", "pig", "boar", "cow", "monkey",
                "parrot", "cockatoo", "bird", "penguin", "rabbit", "bunny", "squirrel",
                "hamster", "lemur", "collie", "geese", "gosling", "lamb",
                "pet", "animal", "animals", "wildlife", "zoo", "farm"],
    "funny_fails": ["fail", "fails", "faceplant", "slip", "fall", "falls", "oops", "wipeout"],
    "pranks": ["prank", "pranks", "scare", "jumpscare", "gotcha"],
    "sports": ["goal", "dunk", "nba", "nfl", "soccer", "football", "basketball", "skate",
               "skateboard", "race", "racing", "crash", "stunt", "gym", "golf", "tennis"],
    "reactions": ["reaction", "reacts", "react", "face", "shocked", "karen", "caught"],
    "unexpected": ["unexpected", "plot twist", "wait", "suddenly", "didn't expect",
                   "out of nowhere", "craziest", "crazy", "wtf"],
}
SUBJECT_WORDS = KEYWORDS["animals"][:-6]          # concrete subjects for copy
SYNONYMS = {"geese": "goose", "gosling": "goose", "goslings": "goose", "collie": "dog",
            "kittens": "kitten", "puppies": "puppy", "hen": "chicken", "lambs": "lamb"}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower().replace("-", " ").replace("_", " "))


def detect(*texts: str, declared: str = "") -> tuple[str, float, str]:
    """→ (category, confidence 0..1, method). A declared category from the
    license record wins; otherwise keyword votes, or ("", 0, "unknown")."""
    if declared in CATEGORIES:
        return declared, 1.0, "declared"
    vocab = {k for kws in KEYWORDS.values() for k in kws}
    words = [w[:-1] if w.endswith("s") and w not in vocab and w[:-1] in vocab else w
             for t in texts if t for w in _words(t)]
    joined = " ".join(words)
    votes = {c: sum(joined.count(k) if " " in k else words.count(k) for k in kws)
             for c, kws in KEYWORDS.items()}
    best = max(votes, key=votes.get)
    total = sum(votes.values())
    if votes[best] == 0:
        return "", 0.0, "unknown"
    return best, round(votes[best] / total, 2), "keywords"


def subject(*texts: str) -> str:
    """Most specific concrete subject mentioned ('goose', 'puppy'), or ''."""
    words = [w for t in texts if t for w in _words(t)]
    for w in words:
        if w in SYNONYMS:
            return SYNONYMS[w]
        if w in SUBJECT_WORDS:
            return w
        if w.endswith("s") and w[:-1] in SUBJECT_WORDS:
            return w[:-1]
    return ""
