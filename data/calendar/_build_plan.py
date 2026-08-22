import json, pathlib

ROOT = pathlib.Path(__file__).parent

B_TREND_DAYS = {3,6,9,12,15,18,21,24,27,30}
A_TREND_DAYS = {5,14,23}
C_TREND_DAYS = {8,19}

A_TOPICS = [
 ("IKEA flat-pack origin", "The flat-pack furniture format traces to a 1956 IKEA designer sawing the legs off a table to fit it in a car — turning shipping cost into the whole business model."),
 ("Blockbuster passed on buying Netflix", "In 2000 Netflix's founders offered to sell to Blockbuster for $50M and were turned down; Blockbuster filed for bankruptcy in 2010."),
 ("Southwest's one-aircraft-type strategy", "Southwest Airlines flies only Boeing 737s across its whole fleet, cutting training, parts and maintenance costs versus mixed-fleet rivals."),
 ("Netflix's DVD-to-streaming pivot", "Reed Hastings shifted Netflix from mailing DVDs to streaming starting 2007, cannibalizing its own core product before a competitor could."),
 ("Amazon's thin-margin reinvestment strategy", "Amazon ran on razor-thin retail margins for years while profits were funneled into building AWS, which became the real profit engine."),
 ("McDonald's real estate business", "McDonald's Corporation owns much of the land under its restaurants and collects rent from franchisees, a model Ray Kroc's financier Harry Sonneborn engineered."),
 ("Gillette's razor-and-blades pricing", "Gillette popularized selling razors cheap (or at a loss) while pricing replacement blades high, a pricing pattern later copied by printers and razors alike."),
 ("Nike owns no factories", "Nike designs and markets shoes but has never owned the factories that make them; all manufacturing is outsourced to contracted partners in Asia."),
 ("Sears catalog dominance to bankruptcy", "Sears pioneered mail-order retail dominance in the early 1900s and filed for bankruptcy in 2018 after failing to adapt to e-commerce."),
 ("Kodak invented and buried the digital camera", "A Kodak engineer built the first digital camera prototype in 1975; Kodak shelved it to protect its film business and later went bankrupt in 2012."),
 ("Amazon's garage origin and Day 1 philosophy", "Jeff Bezos founded Amazon in a Bellevue garage in 1994 and has repeatedly framed the company's survival around staying in perpetual 'Day 1' mode."),
 ("Musk's PayPal payout funded Tesla and SpaceX", "Elon Musk's ~$180M from PayPal's 2002 sale to eBay funded early bets on Tesla and SpaceX, both of which nearly ran out of cash in 2008."),
 ("Warby Parker's direct-to-consumer eyewear model", "Warby Parker cut out licensing and retail markups by selling glasses direct to consumers online starting in 2010, undercutting incumbent pricing."),
 ("Airbnb's 2008 cereal box survival story", "Airbnb's founders funded the company in 2008 by selling novelty cereal boxes ('Obama O's' and 'Cap'n McCain's') during the presidential election."),
 ("Standard Oil's breakup created today's oil giants", "The 1911 Supreme Court breakup of Standard Oil into 34 companies produced firms that evolved into ExxonMobil, Chevron and others."),
 ("Disney's IP acquisition strategy", "Disney's acquisitions of Pixar (2006), Marvel (2009) and Lucasfilm (2012) were bets on owning franchises rather than building new ones from scratch."),
 ("Enron's accounting collapse", "Enron used mark-to-market accounting and off-balance-sheet entities to hide debt and inflate profits before collapsing into bankruptcy in 2001."),
 ("BlackBerry's fall from smartphone leader", "BlackBerry dominated smartphones with physical keyboards before the 2007 iPhone; it was slow to adopt touchscreens and lost its market lead within a few years."),
 ("Costco's Kirkland Signature private-label strategy", "Kirkland Signature, Costco's house brand, has grown to account for roughly a quarter of Costco's total sales by underpricing name brands on the same shelf."),
 ("Toys R Us bankruptcy and private equity debt", "Toys R Us was taken private in a 2005 leveraged buyout that loaded it with debt; it filed for bankruptcy in 2017 partly under that debt burden."),
 ("Walmart's everyday-low-price origins", "Sam Walton built Walmart's growth on aggressive supply-chain bargaining and an everyday-low-price strategy rather than periodic sales."),
 ("Tesla's Gigafactory vertical integration bet", "Tesla built its own battery Gigafactory starting 2014 to control battery supply and cost instead of depending on outside cell makers."),
 ("Levi's 501 jeans origin", "Levi Strauss and Jacob Davis patented copper-riveted work pants in 1873 for miners; the 501 design has stayed in production largely unchanged."),
 ("Coca-Cola's secret formula and the New Coke failure", "Coca-Cola's formula secrecy is a marketing moat; the 1985 'New Coke' reformulation was reversed within 79 days after public backlash."),
 ("Starbucks' site-selection science", "Starbucks uses detailed demographic and traffic-pattern analysis to choose store locations, historically clustering stores densely in target markets."),
 ("LEGO's 2003 near-bankruptcy turnaround", "LEGO nearly collapsed in 2003-2004 after over-diversifying into theme parks and clothing, then recovered by refocusing on its core brick sets."),
 ("Berkshire Hathaway's origin as a failing textile mill", "Warren Buffett's Berkshire Hathaway began as a struggling New England textile manufacturer he took control of in 1965 before turning it into a holding company."),
]

B_TOPICS = [
 ("How the Fed actually moves interest rates", "The Federal Reserve sets a target range for the federal funds rate and uses tools like interest on reserve balances to guide banks toward it — it does not 'print money' to do this."),
 ("What CPI actually measures", "The Consumer Price Index tracks price changes across a fixed basket of goods and services categories tracked by the Bureau of Labor Statistics, not a single price."),
 ("Why an inverted yield curve signals recession risk", "When short-term Treasury yields rise above long-term yields, it has historically preceded most US recessions, reflecting investor expectations of future rate cuts."),
 ("How an IPO actually works", "A company going public runs a roadshow with underwriting banks to gauge investor demand and set a price before shares list on an exchange."),
 ("What a stock split really changes", "A stock split multiplies the number of shares while dividing the price proportionally — the company's total market value and an investor's stake value don't change."),
 ("How short selling works and its unique risk", "Short sellers borrow and sell shares hoping to buy them back cheaper; because a stock's price has no ceiling, potential losses on a short are theoretically unlimited."),
 ("What a bond actually is", "A bond is a loan an investor makes to a government or company, which pays periodic interest and returns principal at maturity."),
 ("Why index funds beat most active managers", "John Bogle launched the first retail index fund at Vanguard in 1976, betting that low-cost broad market tracking would beat costly active stock-picking over time."),
 ("How stock buybacks work", "A buyback is a company repurchasing its own shares on the open market, reducing share count and (all else equal) raising earnings per remaining share."),
 ("What GDP measures and what it leaves out", "Gross Domestic Product totals the market value of goods and services produced in a country, but excludes unpaid work, informal activity and wellbeing measures."),
 ("How the bid-ask spread quietly costs traders", "Every trade crosses a gap between the highest buy offer and lowest sell offer; that spread is a hidden cost paid on every buy-then-sell round trip."),
 ("What a recession technically is", "In the US, recessions are officially dated by the National Bureau of Economic Research based on broad measures like employment and income, not just two negative GDP quarters."),
 ("Why gold became a 'safe haven' asset", "Gold's scarcity and lack of counterparty risk have made it a traditional store of value during currency instability and market stress for centuries."),
 ("ETFs vs mutual funds: the tax efficiency gap", "ETFs typically generate fewer taxable capital-gains distributions than actively managed mutual funds because of how share creation/redemption works in-kind."),
 ("How margin trading amplifies gains and losses", "Borrowing against a brokerage account to buy more securities multiplies both potential gains and potential losses, and can trigger forced selling in a margin call."),
 ("Why the S&P 500 is market-cap weighted", "The S&P 500 weights companies by market value, meaning the largest handful of companies can drive a disproportionate share of the index's total return."),
 ("What quantitative easing actually does", "QE is a central bank buying large volumes of government bonds (and sometimes other assets) to push down long-term interest rates and add liquidity to the financial system."),
 ("How stock market circuit breakers work", "US exchanges pause trading automatically when the S&P 500 falls a set percentage in a session, giving the market a cooling-off period during panic selling."),
 ("What 'priced in' means", "Markets move on expectations, so a stock can drop on 'good' news if the results were already anticipated and priced into the share value beforehand."),
 ("Dollar-cost averaging vs lump-sum investing", "Investing a fixed amount at regular intervals smooths out purchase price over time, trading potential upside from lump-sum timing for reduced timing risk."),
]

C_TOPICS = [
 ("How credit card companies profit even when you pay in full", "Every card swipe generates an interchange fee paid by the merchant to the card issuer, so issuers earn revenue even from cardholders who never carry a balance."),
 ("How mortgage interest front-loads the early years", "Mortgage amortization schedules apply most of each early payment to interest and little to principal, gradually flipping over the life of the loan."),
 ("How fractional reserve banking works", "Banks are required to hold only a portion of deposits in reserve and can lend out the rest, which is how the banking system expands the money supply through lending."),
 ("Where the FICO credit score came from", "The Fair Isaac Corporation introduced the FICO score in 1989 to standardize lending risk assessment across US banks using a single three-digit number."),
 ("Compound interest with a concrete example", "Compounding means interest earns interest on itself; the same principal and rate produce dramatically different totals depending purely on how many compounding periods elapse."),
 ("How insurance companies actually profit", "Insurers price policies using actuarial tables that pool risk across many people, collecting more in premiums than they expect to pay out across the whole pool."),
 ("Why store credit cards carry brutal interest rates", "Retail store credit cards often carry some of the highest APRs in the industry because they're underwritten for approval volume, not for the borrower's benefit."),
 ("How Visa and Mastercard make money without lending", "Visa and Mastercard don't issue cards or lend money directly; they earn fees for running the payment network that routes transactions between banks."),
 ("What a 401k match actually is", "An employer 401k match is additional compensation added only when an employee contributes, functioning as an immediate return on the employee's own contribution."),
 ("How payday loans trap borrowers", "Payday loan fees translate to annualized interest rates that can run into the triple digits, which is easy to miss when the fee is quoted as a flat dollar amount."),
 ("Why your paycheck withholding isn't your final tax bill", "Employers withhold estimated tax from each paycheck using IRS formulas, and the true tax owed is only reconciled the following year when a return is filed."),
 ("How debt consolidation actually works", "Debt consolidation combines multiple debts into a single new loan, which can lower the interest rate paid but doesn't reduce the underlying amount owed."),
 ("Why leasing a car is structured differently than buying", "A car lease charges for the vehicle's depreciation over the lease term plus a finance charge, rather than financing the full purchase price like a loan."),
 ("How buy-now-pay-later apps make money", "BNPL providers earn primarily from merchant fees for driving sales and checkout conversion, with late fees as a secondary revenue source on missed payments."),
 ("What FDIC insurance actually covers", "FDIC deposit insurance protects up to $250,000 per depositor, per bank, per ownership category — not an unlimited guarantee on everything in an account."),
 ("How overdraft fees became a bank revenue stream", "Banks process transactions in ways that can trigger multiple overdraft fees from a single low balance, turning a small shortfall into a recurring revenue source."),
 ("Why 0% balance transfer offers exist", "Card issuers offer 0% balance-transfer promotions banking on a transfer fee upfront and the likelihood some balance survives past the promotional window at full interest."),
 ("How title loans work and why they're risky", "Title loans use a vehicle as collateral for short-term high-interest borrowing, and missed payments can result in repossession of the car."),
 ("Why credit utilization moves your score fast", "The percentage of available credit you're using is one of the most heavily weighted, fastest-changing factors in common credit scoring models."),
 ("How rewards credit cards are funded", "Card rewards are paid for largely out of interchange fees and interest paid by other cardholders who carry balances, not out of the issuer's goodwill."),
 ("Why renters insurance is cheap but often skipped", "Renters insurance is inexpensive relative to the value of belongings and liability protection it covers, but adoption rates remain low compared to homeowners insurance."),
 ("How student loan interest capitalization works", "When unpaid interest is added to a student loan's principal (capitalized), future interest is then charged on that larger balance, compounding the cost."),
 ("What a HELOC actually is", "A home equity line of credit lets a homeowner borrow repeatedly against home equity up to a limit, functioning more like a credit card secured by the house."),
 ("The limits of identity theft protection services", "Identity theft protection services monitor for misuse and help with recovery, but generally cannot prevent a breach or a determined identity thief from acting first."),
 ("Why term life costs so much less than whole life", "Term life insurance only pays out if death occurs within a fixed period and builds no cash value, which is why it costs far less than permanent whole life coverage."),
 ("How check-cashing stores profit from the unbanked", "Check-cashing and prepaid-card services charge fees for basic transactions that a checking account would handle for free, disproportionately affecting unbanked consumers."),
 ("What a credit freeze actually does", "A credit freeze restricts access to your credit report so new accounts generally can't be opened in your name, and by law it's free to place and lift."),
 ("How subscription free trials are engineered", "Free-trial signup flows are commonly designed around auto-conversion to paid billing, requiring an active cancellation before a deadline that's easy to lose track of."),
]

assert len(A_TOPICS) == 27, len(A_TOPICS)
assert len(B_TOPICS) == 20, len(B_TOPICS)
assert len(C_TOPICS) == 28, len(C_TOPICS)

def build():
    a_days = [d for d in range(1,31) if d not in A_TREND_DAYS]
    b_days = [d for d in range(1,31) if d not in B_TREND_DAYS]
    c_days = [d for d in range(1,31) if d not in C_TREND_DAYS]
    assert len(a_days) == 27 and len(b_days) == 20 and len(c_days) == 28

    slots = []
    a_iter = iter(zip(a_days, A_TOPICS))
    b_iter = iter(zip(b_days, B_TOPICS))
    c_iter = iter(zip(c_days, C_TOPICS))
    a_map = dict(a_iter); b_map = dict(b_iter); c_map = dict(c_iter)

    TREND_SPEC = {
        "a": dict(category="business_wealth_story",
                  research_query_tmpl="major US business/M&A/corporate-strategy news story breaking within the last 72 hours"),
        "b": dict(category="markets_economics_education",
                  research_query_tmpl="latest Federal Reserve decision, CPI/jobs report release, or major market-moving macro event within the last 72 hours"),
        "c": dict(category="money_mechanics_finance",
                  research_query_tmpl="recent banking, payments, or consumer-finance news story (fees, regulation, major bank/fintech action) within the last 72 hours"),
    }

    for day in range(1, 31):
        for slot, trend_days, topic_map, cat in [
            ("a", A_TREND_DAYS, a_map, "business_wealth_story"),
            ("b", B_TREND_DAYS, b_map, "markets_economics_education"),
            ("c", C_TREND_DAYS, c_map, "money_mechanics_finance"),
        ]:
            job_id = f"d{day:02d}_{slot}"
            is_trend = day in trend_days
            if is_trend:
                spec = TREND_SPEC[slot]
                slots.append({
                    "job_id": job_id, "day": day, "slot": slot.upper(),
                    "category": spec["category"], "content_type": "trend",
                    "evergreen": False,
                    "topic": "TREND SLOT — researched at publish time",
                    "angle": spec["research_query_tmpl"],
                    "status": "TREND — RESEARCH ON PUBLISH DATE",
                })
            else:
                topic, angle = topic_map[day]
                slots.append({
                    "job_id": job_id, "day": day, "slot": slot.upper(),
                    "category": cat, "content_type": "evergreen",
                    "evergreen": True,
                    "topic": topic, "angle": angle,
                    "status": "PLANNED",
                })
    return slots

if __name__ == "__main__":
    slots = build()
    assert len(slots) == 90
    evergreen = [s for s in slots if s["evergreen"]]
    trend = [s for s in slots if not s["evergreen"]]
    assert len(evergreen) == 75, len(evergreen)
    assert len(trend) == 15, len(trend)
    (ROOT / "master_plan.json").write_text(json.dumps(slots, indent=2), encoding="utf-8")
    print(f"OK: {len(slots)} slots, {len(evergreen)} evergreen, {len(trend)} trend")
