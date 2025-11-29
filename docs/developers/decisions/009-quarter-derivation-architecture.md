# ADR 009: Quarter Derivation Architecture (Q2, Q3, Q4)

**Status:** Accepted
**Date:** 2025-11-28
**Deciders:** Core team
**Supersedes:** ADR 007

## Context

SEC reporting regulations require companies to file cumulative Year-To-Date (YTD) values for certain financial statements (notably Cash Flow per Regulation S-X), while filing individual quarters for others (Income Statement). This creates inconsistent data structure:

- **Income Statement:** Companies report Q1, Q2, Q3, Q4 as individual quarters
- **Cash Flow:** Companies report Q1, 6M YTD, 9M YTD, FY (cumulative)
- **Balance Sheet:** Companies report instant snapshots (Q1, Q2, Q3, Q4, FY)

Users need consistent quarterly data (Q1, Q2, Q3, Q4) for time-series analysis, trend detection, and quarter-over-quarter comparisons.

### The Problem

ADR 007 implemented automatic Q4 derivation in the report layer, but:

1. **Incomplete:** Only derived Q4, not Q2 or Q3 from YTD data
2. **Always-on:** Derivation ran unconditionally, couldn't show raw data
3. **Cash flow broken:** Logic failed for concepts without balance attribute
4. **No transparency:** Users couldn't verify derived vs raw data

**Example - BKE Cash Flow (before fix):**
```
# Report output (Q2, Q3 showing YTD values, not quarters!)
Q1: Operating CF = $29.9M
Q2: Operating CF = $77.5M  ← This is 6M YTD, not Q2!
Q3: Operating CF = $121.2M ← This is 9M YTD, not Q3!
Q4: Operating CF = $242.0M ← This is FY, not Q4!
```

**User expectation:**
```
Q1: $29.9M
Q2: $47.6M  (6M YTD - Q1 = 77.5 - 29.9)
Q3: $43.8M  (9M YTD - 6M YTD = 121.2 - 77.5)
Q4: $120.8M (FY - 9M YTD = 242.0 - 121.2)
```

## Decision

### Architecture: Separation of Concerns

**Principle:** Database stores raw XBRL data exactly as filed; report layer derives calculated data on demand.

This architectural choice provides:
1. **Transparency:** Users can verify against SEC filings
2. **Flexibility:** Support both raw and derived views
3. **Data integrity:** Never modify source data
4. **Reproducibility:** Derivation logic is versioned in code, not data

### Command Behavior

```bash
# Show raw data as filed with SEC (transparent, verifiable)
ep report -t TICKER -g GROUP
# → Q1, 6M YTD, 9M YTD, FY (for cash flow)
# → Q1, Q2, Q3, FY (for operations if no Q4 filed)

# Derive missing quarters and filter to Q1-Q4 only
ep report -t TICKER -g GROUP -q
# → Q1, Q2, Q3, Q4 (consistent across all statement types)

# Show annual data only
ep report -t TICKER -g GROUP -y
# → FY
```

### Quarter Derivation Logic

When `-q` flag is used, derive missing quarters from YTD data:

**Q2 Derivation:**
```
IF 6M YTD exists AND Q1 exists THEN
  Q2 = 6M YTD - Q1
```

**Q3 Derivation (two strategies):**
```
Strategy 1 (preferred):
  IF 9M YTD exists AND 6M YTD exists THEN
    Q3 = 9M YTD - 6M YTD

Strategy 2 (fallback):
  IF 9M YTD exists AND Q1 exists AND Q2 exists THEN
    Q3 = 9M YTD - Q1 - Q2
```

**Q4 Derivation (two strategies):**
```
Strategy 1 (preferred):
  IF FY exists AND 9M YTD exists THEN
    Q4 = FY - 9M YTD

Strategy 2 (fallback):
  IF FY exists AND Q1 exists AND Q2 exists AND Q3 exist THEN
    Q4 = FY - Q1 - Q2 - Q3
```

### Concept Classification: What to Derive vs Copy

Critical challenge: Not all flow concepts are derivable by subtraction.

**Examples:**
- Revenue: Derivable (Q2 revenue = 6M cumulative - Q1)
- Operating Cash Flow: Derivable (Q2 OCF = 6M cumulative - Q1)
- Weighted Average Shares: **NOT derivable** (average of averages ≠ subtraction)
- EPS: Derivable (EPS = Income/Shares, both components derivable)

**Solution:** Use XBRL metadata to classify concepts.

#### Classification Logic

```python
# Stock variables (balance sheet snapshots)
if mode == "instant":
    action = COPY  # Snapshot values, not cumulative

# Flow variables (income, cash flow)
elif mode == "flow":
    balance = concept_balance.get(concept_name)
    tag = concept_tag.get(concept_name, "")

    # Decide if derivable
    is_balance_item = balance in ("debit", "credit")
    is_eps = "earningspershare" in tag.lower()
    is_flow_without_balance = balance is None
    is_average = "average" in tag.lower()

    should_derive = (is_balance_item or is_eps or is_flow_without_balance) and not is_average

    if should_derive:
        action = DERIVE  # Q2 = 6M YTD - Q1
    else:
        action = COPY    # Weighted averages: Q2 = 6M YTD value
```

**Key insight:** Cash flow concepts typically have `balance=None` (not debit/credit) because they represent net flows that can be positive or negative. The fix in this ADR is recognizing `balance=None` as a **derivable** category (unless it's an average).

#### XBRL Metadata

**1. Context Mode**
- Source: `fact.context.isInstantPeriod`
- Values: `instant` (balance sheet) or `flow` (income, cash flow)
- Purpose: Distinguish snapshots from flows

**2. Balance Attribute**
- Source: `fact.concept.balance` (XBRL taxonomy)
- Values: `debit`, `credit`, or `None`
- Examples:
  - `debit`: Assets, Expenses
  - `credit`: Liabilities, Revenue
  - `None`: Cash flow line items, ratios, averages
- Purpose: Identify accounting-based cumulative flows

**3. Concept Tag**
- Source: `fact.qname.localName`
- Purpose: Pattern matching for special cases
- Patterns:
  - `"average"` → Non-additive (weighted average shares)
  - `"earningspershare"` → Derivable exception (critical metric)

### Decision Table

| Concept | Mode | Balance | Tag Pattern | Action | Example |
|---------|------|---------|-------------|--------|---------|
| Total Revenue | flow | credit | RevenueFromContract... | DERIVE | Q2 = 6M YTD - Q1 |
| COGS | flow | debit | CostOfGoodsAndServices... | DERIVE | Q2 = 6M YTD - Q1 |
| Operating CF | flow | None | NetCashProvidedByUsed... | DERIVE | Q2 = 6M YTD - Q1 |
| CapEx | flow | None | PaymentsToAcquire... | DERIVE | Q2 = 6M YTD - Q1 |
| EPS Basic | flow | None | ...earningspershare... | DERIVE | Q2 = 6M YTD - Q1 |
| Avg Shares | flow | None | ...average...shares... | COPY | Q2 = 6M YTD value |
| Total Assets | instant | debit | Assets | COPY | Snapshot at period end |

### Implementation

**File:** `edgar/cli/report.py`

**Changes:**
1. **Conditional derivation** (lines 129-133): Only run when `-q` flag present
2. **Function rename:** `_derive_q4()` → `_derive_quarters()`
3. **Q2/Q3 derivation** (lines 331-363): Implement full quarter derivation
4. **Balance attribute fix** (lines 406-416, 531-541): Handle `balance=None` correctly

**Helper functions:**
- `_derive_quarter_by_subtraction()`: Q2 or Q3 from YTD - previous
- `_derive_quarter_by_double_subtraction()`: Q3 from YTD - Q1 - Q2 (fallback)
- `_derive_quarter_multi_sub()`: Core logic with metadata-based classification

## Consequences

### Positive

1. **Complete quarterly data:** All statement types now yield Q1-Q4
2. **Transparent:** Users can verify raw data without `-q` flag
3. **Cash flow works:** Fixed balance attribute handling for CF statements
4. **Consistent UX:** Same command works for all statement types
5. **Separation of concerns:** Database = raw, report = derived
6. **Safe defaults:** Weighted averages never derived (prevent nonsense)

### Negative

1. **Breaking change:** Old behavior (always derive Q4) now requires `-q`
   - Mitigation: No external users yet (3 GitHub visitors)
   - Mitigation: BKE Makefile always uses `-q` (no regression)

2. **EPS still hardcoded:** Exception handling not generalized
   - Same issue as ADR 007
   - Future work: Identify general pattern for derivable ratios

3. **More complex logic:** Classification rules must handle edge cases
   - Mitigation: Well-tested (BKE covers income, cash flow, balance sheet)
   - Mitigation: Documented decision table

## Examples

### Cash Flow (BKE 2024)

**Raw data (`ep report -t BKE -g CashFlow`):**
```
Period      Operating CF
Q1          $29.9M
6M YTD      $77.5M
9M YTD      $121.2M
FY          $242.0M
```

**Quarterly data (`ep report -t BKE -g CashFlow -q`):**
```
Period      Operating CF    Calculation
Q1          $29.9M         (direct from filing)
Q2          $47.6M         (77.5 - 29.9)
Q3          $43.8M         (121.2 - 77.5)
Q4          $120.8M        (242.0 - 121.2)
```

### Operations (BKE 2024)

**Raw data (`ep report -t BKE -g Operations.EPS`):**
```
Period      EPS Basic
Q1          $0.70
Q2          $0.79
Q3          $0.89
9M YTD      $2.37
FY          $3.92
```

**Quarterly data (`ep report -t BKE -g Operations.EPS -q`):**
```
Period      EPS Basic       Calculation
Q1          $0.70          (direct from filing)
Q2          $0.79          (direct from filing)
Q3          $0.89          (direct from filing)
Q4          $1.55          (3.92 - 2.37)
```

### Shares (BKE 2024) - Copy Example

**Raw data:**
```
Period      Avg Shares
Q1          49,854K
Q2          49,854K
Q3          49,854K
9M YTD      49,854K
FY          49,922K
```

**Quarterly data (`-q`):**
```
Period      Avg Shares      Calculation
Q1          49,854K        (direct)
Q2          49,854K        (direct)
Q3          49,854K        (direct)
Q4          49,922K        (copied from FY, NOT derived!)
```

If Q4 was derived: 49,922 - 49,854 = **68** shares (nonsense!)

## Testing

**Test suite coverage:**
1. ✅ Cash Flow quarterly derivation (Q2, Q3, Q4 from YTD)
2. ✅ Operations EPS derivation (Q4 from FY)
3. ✅ Weighted average shares (copy, not derive)
4. ✅ No regression on existing reports
5. ✅ Raw data mode (no `-q` flag)

**Test data:** BKE (Buckle Inc.) 42 filings (Q2 2015 - Q2 2025)
- Balance Sheet, Income Statement, Cash Flow
- Mix of camelCase (2015-2020) and ALL CAPS (2020+) role names
- Cash flow concepts with `balance=None`
- Weighted average shares

## Alternatives Considered

### Option A: Derive in database (update command)
- **Rejected:** Violates transparency principle
- Pros: Simpler report code
- Cons: Can't verify against SEC filings, derivation logic hidden

### Option B: Always derive (no flag control)
- **Rejected:** Can't show raw data for verification
- Pros: Simpler UX
- Cons: Users can't validate against source documents

### Option C: New command `ep derive`
- **Considered:** Separate command for derivation
- Pros: Explicit operation
- Cons: Extra complexity, `-q` flag is clearer

### Option D: Aggressive default (derive all flows)
- **Rejected:** Same issue as ADR 007
- Breaks weighted averages, too risky

## Future Work

1. **Generalize EPS exception:**
   - Pattern: `"per.*share"` or ratio detection
   - Add `derivable` flag to concept patterns table

2. **Q2/Q3 derivation from direct filings:**
   - Some companies file actual Q2/Q3 (rare)
   - Prefer direct over derived when available

3. **Derivation provenance tracking:**
   - Mark derived values in output
   - `Q4* (derived)` vs `Q4 (filed)`

4. **Sanity checks:**
   - Warn if derived Q4 is negative for revenue
   - Validate sum: Q1+Q2+Q3+Q4 ≈ FY (within rounding)

5. **User overrides:**
   - Add `derivation_mode` to concept_patterns
   - Allow per-concept control: `auto`, `derive`, `copy`, `none`

## Related

- **Supersedes:** ADR 007 (Q4 Derivation Logic)
- **Related:** ADR 003 (Pattern-based extraction), ADR 005 (Workspace model)
- **Implementation:** `edgar/cli/report.py` lines 129-560
- **Tests:** BKE workspace (financial-terminal/bke)
