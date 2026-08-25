"""Machine-readable license record schema for the K70 Scene Engine.

Every asset that can enter automatic production — whether it's a single 3D
model or an entire vendored tool repository — gets one `LicenseEntry`. The
validator (`validator.py`) uses `commercial_use` + `clarity` to decide
whether something is allowed into `catalog/index.py` at all.

`clarity` is deliberately separate from `commercial_use`: a license can be
perfectly permissive (CC0) but still get `clarity="needs_review"` the first
time it's seen, until a human or an automated check confirms the source
actually carries that license (not just a claim in a README).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum


class Clarity(str, Enum):
    VERIFIED = "verified"           # license text read directly from the source, terms unambiguous
    CLAIMED = "claimed"             # source/README claims a license; not independently re-derived
    NEEDS_REVIEW = "needs_review"   # ambiguous, missing, or conflicting signals
    REJECTED = "rejected"           # explicitly excluded — do not use, ever


class CommercialUse(str, Enum):
    YES = "yes"
    NO = "no"
    CONDITIONAL = "conditional"     # e.g. GPL tool used as external process, not vendored/linked
    UNKNOWN = "unknown"


@dataclass
class LicenseEntry:
    asset_id: str                      # stable id, e.g. "gobkit:minion-a01"
    source: str                        # repo or origin name, e.g. "Ariescar/gobkit-free-assets"
    source_url: str
    creator: str = ""
    license_spdx: str = ""             # SPDX id where one applies, e.g. "CC0-1.0", "MIT", "GPL-3.0"
    license_note: str = ""             # free-text nuance (e.g. GPL-tool-as-subprocess reasoning)
    commercial_use: CommercialUse = CommercialUse.UNKNOWN
    attribution_required: bool = False
    clarity: Clarity = Clarity.NEEDS_REVIEW
    local_path: str = ""               # path under tools/k70_scene_engine/vendor/, empty if not vendored
    category: str = ""                 # character / building / prop / tool / index / nature / ...
    tags: list[str] = field(default_factory=list)
    integration_mode: str = "vendored" # "vendored" | "subprocess_only" | "index_pointer" | "excluded"
    checked_at: str = ""               # ISO date the entry was last verified

    def eligible(self) -> bool:
        """Whether this entry may be used by automatic K70 production."""
        if self.clarity in (Clarity.NEEDS_REVIEW, Clarity.REJECTED):
            return False
        return self.commercial_use in (CommercialUse.YES, CommercialUse.CONDITIONAL)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["commercial_use"] = self.commercial_use.value
        d["clarity"] = self.clarity.value
        return d
