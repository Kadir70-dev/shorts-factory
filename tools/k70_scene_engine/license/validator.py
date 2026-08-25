"""Validates LicenseEntry records and filters a catalog down to what
automatic K70 production is actually allowed to touch.

This is intentionally conservative: `validate()` raises on structurally
broken entries (missing source, no SPDX id where one is claimed), and
`filter_eligible()` silently drops (with a logged reason) anything that
doesn't pass `LicenseEntry.eligible()` rather than letting it through.
"""
from __future__ import annotations

from .schema import LicenseEntry, Clarity, CommercialUse


class LicenseValidationError(ValueError):
    pass


def validate(entry: LicenseEntry) -> None:
    if not entry.asset_id:
        raise LicenseValidationError("asset_id is required")
    if not entry.source:
        raise LicenseValidationError(f"{entry.asset_id}: source is required")
    if entry.clarity == Clarity.VERIFIED and not entry.license_spdx and not entry.license_note:
        raise LicenseValidationError(
            f"{entry.asset_id}: clarity=verified but no license_spdx/license_note recorded")
    if entry.commercial_use == CommercialUse.YES and entry.clarity == Clarity.NEEDS_REVIEW:
        raise LicenseValidationError(
            f"{entry.asset_id}: cannot claim commercial_use=yes while clarity=needs_review")


def filter_eligible(entries: list[LicenseEntry]) -> tuple[list[LicenseEntry], list[tuple[LicenseEntry, str]]]:
    """Split entries into (eligible, excluded_with_reason)."""
    eligible: list[LicenseEntry] = []
    excluded: list[tuple[LicenseEntry, str]] = []
    for e in entries:
        validate(e)
        if e.eligible():
            eligible.append(e)
        else:
            reason = (f"clarity={e.clarity.value}" if e.clarity != Clarity.VERIFIED
                      and e.clarity != Clarity.CLAIMED
                      else f"commercial_use={e.commercial_use.value}")
            excluded.append((e, reason))
    return eligible, excluded
