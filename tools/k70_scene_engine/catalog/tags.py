"""Semantic tag vocabulary for the K70 asset catalog.

Kept as a flat, deliberately redundant vocabulary (not a strict taxonomy)
because storyboard queries are semantic ("bank", "investor", "mortgage")
rather than structural. `expand()` adds the finance-domain synonyms a
narration beat is likely to actually use, so a query for "gold" also
surfaces assets tagged "vault" or "bullion" without every indexer having to
know every synonym up front.
"""
from __future__ import annotations

CATEGORIES = [
    "character", "building", "office", "bank", "house", "furniture",
    "vehicle", "computer", "phone", "money_prop", "gold", "vault", "store",
    "factory", "street", "city", "nature", "government", "industrial",
    "tool", "prop",
]

# tag -> extra tags a query for it should also match
SYNONYMS: dict[str, list[str]] = {
    "bank": ["vault", "office", "banker", "finance"],
    "gold": ["vault", "bullion", "money_prop", "xau"],
    "usd": ["money_prop", "dollar", "currency"],
    "investor": ["character", "trader", "business_owner"],
    "trader": ["character", "investor", "computer"],
    "worker": ["character", "employee"],
    "family": ["character", "house"],
    "house": ["building", "mortgage", "residential"],
    "mortgage": ["house", "bank", "loan"],
    "inflation": ["money_prop", "store", "economy"],
    "economy": ["city", "government", "inflation"],
    "meeting": ["office", "character"],
    "shopping": ["store", "money_prop"],
    "computer": ["office", "trader"],
    "city": ["street", "building", "government"],
}


def expand(query_tags: list[str]) -> set[str]:
    out: set[str] = set()
    for t in query_tags:
        t = t.lower().strip()
        out.add(t)
        out.update(SYNONYMS.get(t, []))
    return out
