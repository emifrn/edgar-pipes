# ADR 008: Fact Selection Strategy for Quarterly Reporting

**Status:** Accepted
**Date:** 2025-11-27
**Deciders:** Core team

## Context

When extracting quarterly financial data from SEC XBRL filings, companies use different reporting patterns. Some file standalone quarters (Q1, Q2, Q3), while others file year-to-date periods (6M, 9M). A single filing may also contain multiple facts for the same concept in different contexts (current period + comparative prior year periods).

The system must select the "best" fact for each quarterly period from potentially multiple candidates with different characteristics:

**Example: BKE Q2 2025 filing contains 4 SellingAndMarketingExpense facts:**
1. Q2 2025 quarter: $73.9M (92 days: May 4 - Aug 3, 2025)
2. Q2 2024 quarter: $70.7M (92 days: May 5 - Aug 4, 2024) ← comparative period
3. 6M YTD 2025: $141.1M (183 days: Feb 2 - Aug 3, 2025)
4. 6M YTD 2024: $134.5M (183 days: Feb 4 - Aug 4, 2024) ← comparative period

**Challenge:** Which fact should we select for "Q2 2025"?

### Reporting Pattern Variations

**Pattern A: Quarter-only (Simple)**
- Example: Most companies, BKE historical
- Reports: Q1 quarter, Q2 quarter, Q3 quarter, FY year
- Selection: Direct match, no derivation needed

**Pattern B: YTD-based (Complex)**
- Example: Many large companies
- Reports: Q1 quarter, 6M YTD, 9M YTD, FY year
- Selection: Use YTD for derivation (Q2 = 6M - Q1, Q3 = 9M - 6M)

**Pattern C: Mixed (Transition)**
- Example: BKE Q2 2025
- Reports: Q1 quarter, Q2 quarter + 6M YTD (both!), FY year
- Selection: Prefer direct quarter over YTD

## Decision

We implement a **preference-based selection strategy** that:

1. **Prefers direct facts over derived**: Quarter mode preferred over YTD modes
2. **Uses doc_period_end for disambiguation**: When multiple candidates of the same mode exist, pick the one with end_date closest to the filing's doc_period_end
3. **Falls back to YTD with derivation**: When direct facts unavailable, use YTD for derivation

### Period Mode Classification

Facts are classified by duration (`_mode_from_days`):

| Mode | Days Range | Description | Example |
|------|------------|-------------|---------|
| `instant` | 1 | Point-in-time | Balance sheet on May 3 |
| `quarter` | 88-95 | Standalone quarter | Q2: May 4 - Aug 3 (92 days) |
| `semester` | 170-185 | 6-month YTD | Jan 1 - Aug 3 (183 days) |
| `threeQ` | 260-275 | 9-month YTD | Jan 1 - Nov 3 (275 days) |
| `year` | 350-373 | Full year | Jan 1 - Dec 31 (365 days) |
| `period` | other | Non-standard | Any other duration |

### Selection Logic by Period

#### Q1 Selection
```python
def get_best_q1(facts, past_periods=None, doc_period_end=None):
    # 1. Filter to quarter-mode facts only
    candidates = [f for f in facts if f["mode"] == "quarter"]

    # 2. Prefer fact closest to doc_period_end (handles comparative periods)
    if doc_period_end and candidates:
        return min(candidates, key=lambda f: _date_distance(f["end_date"], doc_period_end))

    # 3. Otherwise take first
    return candidates[0] if candidates else None
```

**Strategy:** Simple - always use quarter mode, disambiguate by date.

#### Q2 Selection
```python
def get_best_q2(facts, past_periods=None, doc_period_end=None):
    has_q1 = any(p == "Q1" for _, p in past_periods)
    quarter_candidates = [f for f in facts if f["mode"] == "quarter"]
    semester_candidates = [f for f in facts if f["mode"] == "semester"]

    # 1. PREFER quarter mode if available (direct Q2 reporting)
    if quarter_candidates:
        if doc_period_end:
            return min(quarter_candidates, key=lambda f: _date_distance(f["end_date"], doc_period_end))
        return quarter_candidates[0]

    # 2. FALLBACK to semester (6M YTD) only if we have Q1 for derivation
    if semester_candidates and has_q1:
        if doc_period_end:
            return min(semester_candidates, key=lambda f: _date_distance(f["end_date"], doc_period_end))
        return semester_candidates[0]

    return None
```

**Strategy:** Prefer direct quarter, fall back to semester if Q1 exists for derivation.

**Key change (Bug fix #2b):** Previously preferred semester when `has_q1=True`, even if quarter facts existed. This caused BKE Q2 2025 to select 6M YTD ($141M) instead of direct quarter ($73.9M).

#### Q3 Selection
```python
def get_best_q3(facts, past_periods=None, doc_period_end=None):
    past = {(m, p) for m, p in past_periods}
    threeQ_candidates = [f for f in facts if f["mode"] == "threeQ"]
    quarter_candidates = [f for f in facts if f["mode"] == "quarter"]

    # Can we derive from 9M YTD?
    can_derive_from_threeQ = (
        ("semester", "Q2") in past or
        (("quarter", "Q1") in past and ("quarter", "Q2") in past)
    )

    # 1. PREFER threeQ (9M YTD) if we can derive Q3
    if threeQ_candidates and can_derive_from_threeQ:
        if doc_period_end:
            return min(threeQ_candidates, key=lambda f: _date_distance(f["end_date"], doc_period_end))
        return threeQ_candidates[0]

    # 2. FALLBACK to quarter (direct Q3)
    if quarter_candidates:
        if doc_period_end:
            return min(quarter_candidates, key=lambda f: _date_distance(f["end_date"], doc_period_end))
        return quarter_candidates[0]

    return None
```

**Strategy:** Prefer 9M YTD for derivation if prior periods exist, otherwise use direct quarter.

**Note:** This differs from Q2 logic which prefers direct quarter. The rationale is that 9M YTD derivation (Q3 = 9M - 6M) may be more accurate than filed Q3 quarters in some cases. This preference could be reconsidered for consistency.

#### FY Selection
```python
def get_best_fy(facts, past_periods) -> dict | None:
    options = [f for f in facts if f.get("mode") in ("year", "quarter", "period")]
    rank = {"year": 0, "quarter": 1, "period": 2}
    return min(options, key=lambda f: rank.get(f["mode"], 99), default=None)
```

**Strategy:** Prefer year mode, fall back to quarter or period.

**Known issue:** Doesn't use `doc_period_end` for disambiguation, so may select wrong year when filing contains multiple FY facts (current + comparative).

### Date Distance Calculation

When multiple facts of the same mode exist (e.g., Q2 2025 + Q2 2024), we prefer the one closest to the filing's `doc_period_end`:

```python
def _date_distance(end_date, doc_period_end_str):
    """Calculate days between fact end_date and filing doc_period_end."""
    end_dt = end_date.date() if hasattr(end_date, 'date') else end_date
    doc_dt = datetime.fromisoformat(doc_period_end_str).date()
    return abs((end_dt - doc_dt).days)
```

**Example:**
- Filing doc_period_end: 2025-08-02
- Fact #1 end_date: 2025-08-03 (distance = 1 day) ← **Selected**
- Fact #2 end_date: 2024-08-04 (distance = 364 days)

## Consequences

### Positive

1. **Correct period selection:** Prefers current year over comparative prior year
2. **Prefers filed facts over derivation:** Direct quarter facts used when available
3. **Supports both reporting patterns:** Works with quarter-only and YTD-based filings
4. **XBRL-native solution:** Uses standard context metadata (start_date, end_date, mode)

### Negative

1. **Inconsistent preference:** Q2 prefers quarter > YTD, but Q3 prefers YTD > quarter
   - Could be unified for consistency
   - Current Q3 logic assumes YTD derivation more accurate

2. **FY selection incomplete:** Doesn't use doc_period_end
   - May select wrong year when comparative FY facts present
   - Should be fixed for consistency

3. **No validation of derivation dependencies:**
   - When selecting semester for Q2, assumes Q1 exists and is valid
   - When selecting threeQ for Q3, assumes prior periods exist
   - Actual derivation happens later in report.py, errors may surface late

### Bug Fixes Applied

**Bug #2a: Comparative period selection**
- **Problem:** When filing contains Q2 2024 + Q2 2025, selected first in iteration order
- **Fix:** Use `doc_period_end` to prefer fact with closest end_date
- **Impact:** BKE Q2 2025 now correctly uses 2025 data instead of 2024

**Bug #2b: Quarter vs YTD preference**
- **Problem:** `get_best_q2` preferred semester when `has_q1=True`, even if quarter existed
- **Fix:** Check quarter candidates first, use semester only as fallback
- **Impact:** BKE Q2 2025 now uses $73.9M (direct quarter) instead of $141M (6M YTD)

## Examples

### Case 1: Quarter-only filing (Pattern A)
```
Filing contains: Q1 quarter, Q2 quarter, Q3 quarter, FY year
Selection:
  Q1 → quarter (92 days)
  Q2 → quarter (92 days)
  Q3 → quarter (92 days)
  Q4 → derive from FY - Q1 - Q2 - Q3
```

### Case 2: YTD-based filing (Pattern B)
```
Filing contains: Q1 quarter, 6M YTD, 9M YTD, FY year
Selection:
  Q1 → quarter (92 days)
  Q2 → semester (183 days), derive Q2 = 6M - Q1
  Q3 → threeQ (275 days), derive Q3 = 9M - 6M
  Q4 → derive from FY - Q1 - Q2 - Q3
```

### Case 3: Mixed filing with comparative periods (Pattern C)
```
Filing contains:
  Q1 2025 quarter, Q2 2025 quarter, 6M 2025 YTD (current year)
  Q1 2024 quarter, Q2 2024 quarter, 6M 2024 YTD (comparative)

Selection using doc_period_end = 2025-08-02:
  Q1 → quarter (2025-05-03, distance=91 days) over quarter (2024-05-04, distance=456 days)
  Q2 → quarter (2025-08-03, distance=1 day) over:
       - quarter (2024-08-04, distance=364 days)
       - semester (2025-08-03, distance=1 day) ← same distance, but quarter preferred!
```

## Alternatives Considered

### Option A: Always prefer direct facts
- **Rejected for Q3:** Some filings have unreliable Q3 quarters, 9M YTD more accurate
- Could revisit if evidence shows direct quarter is consistently better

### Option B: Always prefer YTD for derivation
- **Rejected:** When both exist, direct filing is more authoritative
- YTD introduces rounding errors from subtraction

### Option C: User configuration per company
- **Deferred:** Could add preference setting to concept_patterns or ft.toml
- Adds complexity, current logic handles most cases

### Option D: Machine learning model
- **Rejected:** Overkill for rule-based problem
- XBRL metadata provides sufficient signals

## Future Work

### High Priority

1. **Add doc_period_end to FY selection**
   - Currently missing, may select wrong year for comparative FY facts
   - Simple fix: follow same pattern as Q1/Q2 selection

2. **Validate derivation dependencies**
   - When selecting YTD mode, verify required prior periods exist
   - Return error or warning if derivation impossible

### Medium Priority

3. **Reconsider Q3 preference logic**
   - Should Q3 prefer direct quarter like Q2?
   - Or is there evidence that 9M YTD derivation is more accurate?
   - Document rationale either way

4. **Add selection metadata to output**
   - Mark which facts were "direct" vs "YTD" vs "derived"
   - Help users understand data provenance

### Low Priority

5. **Support for custom preferences**
   - Allow per-company or per-concept overrides
   - Example: `concept_patterns.selection_mode = 'prefer_quarter'|'prefer_ytd'|'auto'`

## Related

- ADR 007: Q4 Derivation Logic (derivation of Q4 from FY and prior quarters)
- ADR 003: Pattern-based extraction (concept pattern matching)
- Module docs: xbrl.md (fact extraction), cli.md (update command)
- XBRL Specification: context period types (instant vs duration)

## Testing

For each selection function, test cases should cover:
- Single mode (normal case)
- Multiple candidates of same mode (comparative periods) → uses doc_period_end
- Multiple modes (quarter + YTD) → uses preference logic
- Missing modes (no quarter available) → uses fallback or returns None
- Cross-year comparisons (2024 + 2025 in same filing) → uses doc_period_end
