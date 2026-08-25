"""Reusable finance scene templates (brief section 9).

Each template is an ordered list of `Shot`s: a suggested VisualMode, a
catalog tag query to pull supporting assets/props, and a short beat
description a storyboard author (human or the existing Director) can drop
narration into. These are STARTING POINTS the visual-mode selector can
override per actual narration -- not a rigid script.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..visual_mode.modes import VisualMode


@dataclass
class Shot:
    beat: str
    mode: VisualMode
    tags: list[str] = field(default_factory=list)
    character_id: str | None = None


@dataclass
class SceneTemplate:
    concept: str
    title: str
    shots: list[Shot]


TEMPLATES: dict[str, SceneTemplate] = {

    "forex": SceneTemplate("forex", "Forex: USD <-> EUR", [
        Shot("Establish the pair", VisualMode.DATA_CHART, ["usd", "economy"]),
        Shot("Exchange-rate movement", VisualMode.DATA_CHART, ["usd"]),
        Shot("Bid/ask/spread explainer", VisualMode.MOTION_GRAPHIC, []),
        Shot("Currency strength comparison", VisualMode.DATA_CHART, []),
    ]),

    "xauusd": SceneTemplate("xauusd", "XAU/USD: Gold vs. the Dollar", [
        Shot("Gold bars, real macro", VisualMode.REAL_IMAGE, ["gold", "vault"]),
        Shot("USD strength context", VisualMode.MOTION_GRAPHIC, ["usd"]),
        Shot("Interest-rate / real-yield mechanic", VisualMode.MOTION_GRAPHIC, []),
        Shot("Safe-haven demand", VisualMode.REAL_STOCK, ["economy"]),
    ]),

    "interest_rates": SceneTemplate("interest_rates", "Interest Rates", [
        Shot("Generic central bank building", VisualMode.THREE_D_ENVIRONMENT, ["government", "bank"]),
        Shot("Rate indicator moves", VisualMode.MOTION_GRAPHIC, []),
        Shot("Borrowing cost rises", VisualMode.THREE_D_CHARACTER, ["worker"], character_id="worker"),
        Shot("Consumer/business impact", VisualMode.REAL_STOCK, ["store"]),
    ]),

    "inflation": SceneTemplate("inflation", "Inflation", [
        Shot("Character with money", VisualMode.THREE_D_CHARACTER, ["character", "money_prop"], character_id="sarah"),
        Shot("Basket of goods, prices increase", VisualMode.THREE_D_ENVIRONMENT, ["store"]),
        Shot("Purchasing power decreases", VisualMode.MOTION_GRAPHIC, []),
    ]),

    "compound_interest": SceneTemplate("compound_interest", "Compound Interest", [
        Shot("Starting investment", VisualMode.THREE_D_CHARACTER, ["investor"], character_id="investor"),
        Shot("Monthly contribution", VisualMode.MOTION_GRAPHIC, ["money_prop"]),
        Shot("Timeline advances", VisualMode.MOTION_GRAPHIC, []),
        Shot("Portfolio growth chart", VisualMode.DATA_CHART, []),
    ]),

    "credit_cards": SceneTemplate("credit_cards", "Credit Cards", [
        Shot("Consumer makes a purchase", VisualMode.THREE_D_CHARACTER, ["character", "store"], character_id="john"),
        Shot("Balance / APR explainer", VisualMode.MOTION_GRAPHIC, []),
        Shot("Interest accumulates over time", VisualMode.DATA_CHART, []),
    ]),

    "credit_score": SceneTemplate("credit_score", "Credit Score", [
        Shot("Borrower profile", VisualMode.THREE_D_CHARACTER, ["character"], character_id="worker"),
        Shot("Payment history / utilization factors", VisualMode.MOTION_GRAPHIC, []),
        Shot("Score moves on a gauge", VisualMode.DATA_CHART, []),
    ]),

    "mortgage": SceneTemplate("mortgage", "Mortgage", [
        Shot("Buyer character", VisualMode.THREE_D_CHARACTER, ["character", "house"], character_id="sarah"),
        Shot("House exterior", VisualMode.THREE_D_ENVIRONMENT, ["house"]),
        Shot("Bank / loan handoff", VisualMode.THREE_D_ENVIRONMENT, ["bank"]),
        Shot("Interest & monthly payment breakdown", VisualMode.DATA_CHART, []),
    ]),

    "stock_market": SceneTemplate("stock_market", "Stock Market", [
        Shot("Company / listed business", VisualMode.THREE_D_ENVIRONMENT, ["office", "building"]),
        Shot("Shares & investors", VisualMode.THREE_D_CHARACTER, ["investor"], character_id="investor"),
        Shot("Market price movement", VisualMode.DATA_CHART, []),
    ]),

    "ipo": SceneTemplate("ipo", "IPO", [
        Shot("Company preparing to list", VisualMode.THREE_D_ENVIRONMENT, ["office", "building"]),
        Shot("Investment bank involvement", VisualMode.THREE_D_ENVIRONMENT, ["bank", "office"]),
        Shot("Market participants / price discovery", VisualMode.DATA_CHART, []),
    ]),

    "recession": SceneTemplate("recession", "Recession", [
        Shot("Businesses under pressure", VisualMode.THREE_D_ENVIRONMENT, ["factory", "office"]),
        Shot("Workers affected", VisualMode.THREE_D_CHARACTER, ["worker"], character_id="worker"),
        Shot("Consumer spending declines", VisualMode.REAL_STOCK, ["store"]),
        Shot("Economic indicators", VisualMode.DATA_CHART, []),
    ]),

    "retirement": SceneTemplate("retirement", "Retirement / 401(k)", [
        Shot("Worker character", VisualMode.THREE_D_CHARACTER, ["worker"], character_id="worker"),
        Shot("Employer contribution", VisualMode.MOTION_GRAPHIC, ["money_prop"]),
        Shot("Long-term investment growth", VisualMode.DATA_CHART, []),
    ]),
}


def get(concept: str) -> SceneTemplate:
    try:
        return TEMPLATES[concept]
    except KeyError:
        raise KeyError(f"unknown finance scene template '{concept}'; known: {sorted(TEMPLATES)}")
