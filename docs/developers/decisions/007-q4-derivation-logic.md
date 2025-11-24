# ADR 007: Q4 Derivation Logic Using XBRL Metadata

**Status:** Accepted
**Date:** 2025-11-23
**Deciders:** Core team

## Context

Most companies file quarterly reports (10-Q) for Q1, Q2, Q3 and an annual report (10-K) for the full fiscal year (FY), but not a separate Q4 report. This creates a challenge when generating quarterly financial reports: Q4 values must be derived from available data.

The naive approach of always deriving Q4 as `Q4 = FY - Q1 - Q2 - Q3` works for cumulative flow concepts (revenue, expenses, net income) but fails for non-cumulative metrics:

**Problem case - Weighted Average Shares:**
- Q1: 49,854,000 shares
- Q2: 49,854,000 shares
- Q3: 49,854,000 shares
- FY: 49,922,000 shares
- Q4 (if derived): **-98,958,000** ❌ (nonsensical negative value)
- Q4 (correct): **49,922,000** (should copy FY value)

The fundamental issue is that weighted average shares are period-based averages, not cumulative totals. You cannot derive a quarterly average from other averages using subtraction.

## Decision

We implement an intelligent Q4 derivation strategy using XBRL metadata to distinguish between cumulative and non-cumulative concepts:

### Derivation Logic

```python
if mode == "instant":
    # Balance sheet items → copy FY value
    Q4 = FY
elif balance in ("debit", "credit"):
    # Cumulative flows → derive by subtraction
    Q4 = FY - Q1 - Q2 - Q3
elif "average" in tag.lower():
    # Weighted averages → copy FY value
    Q4 = FY
elif "earningspershare" in tag.lower():
    # EPS exception → derive (important metric)
    Q4 = FY - Q1 - Q2 - Q3
else:
    # Conservative default → copy FY
    Q4 = FY
```

### XBRL Metadata Used

**1. Context Mode (`instant` vs `duration`)**
- Extracted from: `fact.context.isInstantPeriod` / `fact.context.isStartEndPeriod`
- Stored in: `contexts.mode` table
- Purpose: Distinguishes balance sheet items (instant) from income statement items (duration/flow)

**2. Balance Attribute (`debit`, `credit`, or `None`)**
- Extracted from: `fact.concept.balance` (XBRL taxonomy schema)
- Stored in: `concepts.balance` table (added in this ADR)
- Purpose: Identifies cumulative accounting flows that follow debit/credit rules
- Examples:
  - `debit`: Assets, Expenses (COGS, SG&A)
  - `credit`: Liabilities, Equity, Revenue, Income
  - `None`: Ratios, counts, percentages, averages

**3. Concept Tag**
- Extracted from: `fact.qname.localName`
- Stored in: `concepts.tag` table
- Purpose: Pattern matching for special cases (averages, EPS)

### Implementation Details

**Schema Changes:**
```sql
ALTER TABLE concepts ADD COLUMN balance TEXT;  -- 'debit', 'credit', or NULL
```

**Extraction (edgar/xbrl/arelle.py):**
```python
def extract_concepts_by_role(model, role):
    # ...
    out.append({
        "taxonomy": taxonomy,
        "tag": tag,
        "name": f.concept.label(),
        "balance": f.concept.balance,  # NEW
    })
```

**Q4 Derivation (edgar/cli/report.py):**

The `_derive_q4()` function receives metadata through the pipeline:
1. Query includes `c.balance` from concepts table
2. Facts include `balance` and `tag` fields
3. `_pivot_facts()` tracks metadata per concept
4. `_derive_q4()` applies logic based on metadata

### Rationale for Conservative Default

The logic uses a **conservative default** (copy FY) for unknown cases because:

1. **Safety:** Wrong derivation is more harmful than missing derivation
   - Deriving weighted averages produces nonsensical negative values
   - Copying FY for a derivable concept just duplicates the annual value

2. **Explicit Allowlist:** We only derive when confident:
   - Balance sheet (instant mode) → Always copy
   - Has balance attribute → Known cumulative flow, safe to derive
   - Contains "average" → Known non-cumulative, copy FY
   - EPS exception → Critical metric, explicitly derive

3. **EPS Exception:** While not ideal to have hardcoded exceptions, EPS is:
   - A critical financial metric present in all reports
   - Derivable (EPS = NetIncome / Shares, both components are cumulative/derivable)
   - Worth special handling until a more general solution emerges

## Consequences

### Positive

1. **Correct weighted average handling:** Share counts now show ~49M instead of -100M
2. **Revenue/expenses still work:** Cumulative flows correctly derived using balance attribute
3. **EPS works correctly:** Both derived Q4 values and precision rounding working
4. **XBRL-native solution:** Uses standard taxonomy metadata, not heuristics
5. **Safe defaults:** Unknown metrics default to safe behavior (copy FY)

### Negative

1. **EPS hardcoded exception:** Not a general solution, feels brittle
   - Future work: Identify more general rule (e.g., "per-share" pattern?)
   - Alternative: Maintain allowlist of derivable ratios in database

2. **May miss derivable ratios:** Conservative default means some derivable metrics might be copied instead
   - Impact: Shows FY value for Q4 instead of true quarterly value
   - Mitigation: Add explicit patterns as needed (like EPS)

3. **Schema change required:** Existing databases need regeneration to populate balance column
   - Impact: One-time migration cost
   - Mitigation: Balance is NULL-safe, old databases still work (defaults to copy FY)

### Examples

**Revenue (balance=credit, derivable):**
```
Q1: $275.3M  Q2: $282.1M  Q3: $294.5M  Q4: $248.8M (derived)  FY: $1,100.7M ✓
```

**Weighted Average Shares (balance=None, tag contains "Average"):**
```
Q1: 49,854K  Q2: 49,854K  Q3: 49,854K  Q4: 49,922K (copied)  FY: 49,922K ✓
```

**EPS (balance=None, tag contains "EarningsPerShare"):**
```
Q1: $0.87  Q2: $0.92  Q3: $1.05  Q4: $1.60 (derived)  FY: $4.44 ✓
```

## Alternatives Considered

### Option A: Always derive (original implementation)
- **Rejected:** Produces wrong results for weighted averages
- Simpler code but incorrect for important metrics

### Option B: Never derive, always copy FY
- **Rejected:** Q4 would show FY values for revenue/expenses
- Correct but not useful for quarterly analysis

### Option C: Aggressive default (derive unless "average")
- **Rejected:** Too risky for unknown metrics
- May produce wrong results for undiscovered edge cases

### Option D: User configuration per concept
- **Considered but deferred:** Could add `derivation_mode` column to concept_patterns
- More flexible but requires user knowledge and maintenance
- Could be added later if EPS exception grows into larger allowlist

## Future Work

1. **Replace EPS exception with general pattern:**
   - Investigate "per-share" or "ratio" patterns in XBRL
   - Check if `concept.type` or other metadata can identify derivable ratios

2. **Add derivation_mode to concept_patterns:**
   - Allow users to override default behavior per concept
   - Values: `auto` (use logic), `derive`, `copy`, `none`

3. **Track derivation metadata in output:**
   - Mark which Q4 values were derived vs copied
   - Help users understand data provenance

4. **Validate derived values:**
   - Sanity check derived Q4 (e.g., should be positive for revenue)
   - Warn on suspicious results

## Related

- ADR 003: Pattern-based extraction
- Module docs: xbrl.md (fact extraction), cli.md (report generation)
- XBRL Specification: balance attribute defined in taxonomy schemas
