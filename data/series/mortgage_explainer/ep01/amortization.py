"""Real, verified mortgage amortization calculator for the K70 mortgage
long-form video. Standard fixed-rate amortizing-loan formula -- not
invented, not eyeballed. All figures the narration cites are read from
this script's own output, not typed in by hand.

Scenario (explicitly hypothetical/illustrative -- stated as such in the
video itself, per brief instructions):
  - Home price: $500,000
  - Down payment: 10% ($50,000) -- chosen specifically so PMI genuinely
    applies to this worked example (brief section 8 asks for "PMI when
    applicable"; a 20%-down scenario wouldn't trigger it at all).
  - Loan principal: $450,000
  - Term: 30-year fixed
  - Rate: 6.5% annual, HYPOTHETICAL EXAMPLE (not a live quoted rate)
  - Property tax / insurance / PMI: illustrative assumptions, explicitly
    labeled as such, not asserted as universal figures.
"""
from __future__ import annotations
import json

HOME_PRICE = 500_000
DOWN_PAYMENT_PCT = 0.10
DOWN_PAYMENT = round(HOME_PRICE * DOWN_PAYMENT_PCT)
PRINCIPAL = HOME_PRICE - DOWN_PAYMENT
ANNUAL_RATE = 0.065
TERM_YEARS = 30
N_MONTHS = TERM_YEARS * 12
MONTHLY_RATE = ANNUAL_RATE / 12

# Illustrative-only assumptions, clearly distinguished from P&I in the video
PROPERTY_TAX_ANNUAL_RATE = 0.011      # 1.1% of home value/yr -- illustrative
INSURANCE_MONTHLY = 150.0             # illustrative flat estimate
PMI_ANNUAL_RATE = 0.0075              # 0.75% of loan balance/yr -- illustrative, within
                                       # the commonly-cited ~0.5-1.5% industry range
PMI_CANCEL_LTV = 0.78                 # CFPB-verified automatic-termination trigger

EXTRA_MONTHLY_PRINCIPAL = 300.0       # extra-payment comparison scenario


def monthly_pi(principal: float, monthly_rate: float, n_months: int) -> float:
    if monthly_rate == 0:
        return principal / n_months
    return principal * (monthly_rate * (1 + monthly_rate) ** n_months) / \
        ((1 + monthly_rate) ** n_months - 1)


def amortize(principal: float, annual_rate: float, n_months: int,
            extra_monthly: float = 0.0) -> list[dict]:
    monthly_rate = annual_rate / 12
    payment = monthly_pi(principal, monthly_rate, n_months)
    balance = principal
    rows = []
    month = 0
    while balance > 0.01 and month < n_months + 600:  # safety cap
        month += 1
        interest = balance * monthly_rate
        principal_paid = payment - interest + extra_monthly
        if principal_paid > balance:
            principal_paid = balance
        balance -= principal_paid
        rows.append({"month": month, "interest": interest, "principal": principal_paid,
                    "balance": max(balance, 0.0)})
        if balance <= 0.01:
            break
    return rows


def summarize(rows: list[dict], home_value: float) -> dict:
    total_interest = sum(r["interest"] for r in rows)
    total_principal = sum(r["principal"] for r in rows)
    months_paid = len(rows)
    # first full month of each labeled year (month 1 = year 1)
    def year_row(y):
        idx = min(y * 12, len(rows)) - 1
        return rows[idx] if 0 <= idx < len(rows) else None
    y1, y15, y30 = year_row(1), year_row(15), year_row(min(30, months_paid // 12) or 1)
    ltv_target_balance = home_value * PMI_CANCEL_LTV
    pmi_drop_month = next((r["month"] for r in rows if r["balance"] <= ltv_target_balance), None)
    return {
        "months_paid": months_paid,
        "years_paid": round(months_paid / 12, 2),
        "total_interest": round(total_interest, 2),
        "total_principal": round(total_principal, 2),
        "total_paid": round(total_interest + total_principal, 2),
        "year1_interest_share": round(y1["interest"] / (y1["interest"] + y1["principal"]), 4) if y1 else None,
        "year15_interest_share": round(y15["interest"] / (y15["interest"] + y15["principal"]), 4) if y15 else None,
        "year30_interest_share": round(y30["interest"] / (y30["interest"] + y30["principal"]), 4) if y30 else None,
        "pmi_drop_month": pmi_drop_month,
        "pmi_drop_year": round(pmi_drop_month / 12, 1) if pmi_drop_month else None,
    }


def main():
    payment_pi = monthly_pi(PRINCIPAL, MONTHLY_RATE, N_MONTHS)
    base_rows = amortize(PRINCIPAL, ANNUAL_RATE, N_MONTHS)
    base_summary = summarize(base_rows, HOME_PRICE)

    extra_rows = amortize(PRINCIPAL, ANNUAL_RATE, N_MONTHS, extra_monthly=EXTRA_MONTHLY_PRINCIPAL)
    extra_summary = summarize(extra_rows, HOME_PRICE)

    # illustrative escrow pieces
    property_tax_monthly = HOME_PRICE * PROPERTY_TAX_ANNUAL_RATE / 12
    pmi_monthly_initial = PRINCIPAL * PMI_ANNUAL_RATE / 12
    total_monthly_payment_initial = payment_pi + property_tax_monthly + INSURANCE_MONTHLY + pmi_monthly_initial

    # rate comparison (same principal/term, different hypothetical rates)
    rate_comparison = []
    for r in (0.055, 0.065, 0.075):
        pmt = monthly_pi(PRINCIPAL, r / 12, N_MONTHS)
        rows = amortize(PRINCIPAL, r, N_MONTHS)
        s = summarize(rows, HOME_PRICE)
        rate_comparison.append({"rate": r, "monthly_pi": round(pmt, 2),
                                "total_interest": s["total_interest"]})

    out = {
        "assumptions": {
            "home_price": HOME_PRICE, "down_payment_pct": DOWN_PAYMENT_PCT,
            "down_payment": DOWN_PAYMENT, "principal": PRINCIPAL,
            "annual_rate_hypothetical": ANNUAL_RATE, "term_years": TERM_YEARS,
            "property_tax_annual_rate_illustrative": PROPERTY_TAX_ANNUAL_RATE,
            "insurance_monthly_illustrative": INSURANCE_MONTHLY,
            "pmi_annual_rate_illustrative": PMI_ANNUAL_RATE,
            "pmi_cancel_ltv_cfpb_verified": PMI_CANCEL_LTV,
            "extra_monthly_principal": EXTRA_MONTHLY_PRINCIPAL,
        },
        "monthly_pi": round(payment_pi, 2),
        "monthly_property_tax_illustrative": round(property_tax_monthly, 2),
        "monthly_insurance_illustrative": INSURANCE_MONTHLY,
        "monthly_pmi_initial_illustrative": round(pmi_monthly_initial, 2),
        "total_monthly_payment_initial_illustrative": round(total_monthly_payment_initial, 2),
        "base_schedule_summary": base_summary,
        "extra_payment_schedule_summary": extra_summary,
        "interest_saved_with_extra_payment": round(
            base_summary["total_interest"] - extra_summary["total_interest"], 2),
        "months_saved_with_extra_payment": base_summary["months_paid"] - extra_summary["months_paid"],
        "rate_comparison": rate_comparison,
    }
    print(json.dumps(out, indent=2))
    with open("data/series/mortgage_explainer/ep01/amortization_results.json", "w") as f:
        json.dump(out, f, indent=2)
    return out


if __name__ == "__main__":
    main()
