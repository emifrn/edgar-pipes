# Facts Import Implementation Plan

**Status:** Ready to implement
**Date:** 2025-10-12
**Context:** Session after successful database refactoring (all IDs converted to short form)

---

## Goal

Implement the `update` command to import XBRL facts from filings into the database.

## Strategy: Pragmatic Hybrid

**Storage:** Store ALL facts including dimensional data
**Queries:** Default to consolidated facts, enable dimensional queries later
**Use Case:** Immediate focus on consolidated quarterly analysis, future segment expansion

## Current State

### What Works ✅

- **Database schema:** Ready for facts with dimensions
- **xbrl/facts.py:** Core extraction logic complete
  - `get_concept()` - Extract taxonomy/tag
  - `make_record()` - Convert to DB format (returns `"cid"` ✅)
  - `is_consolidated()` - Check if fact has no dimensions
  - `get_best_q1/q2/q3/fy()` - Smart quarterly selection
- **xbrl/arelle.py:** XBRL parsing complete
  - `load_model()` - Load from URL
  - `role_facts()` - Get facts for a role
  - `extract_dei()` - Extract fiscal period info
- **cache.py:** Entity and filing resolution working
  - `resolve_entities()` - Get companies by ticker
  - `resolve_xbrl_url()` - Get XBRL file URL

### What's Broken ❌

- **cli/update.py:** Old code with wrong function names
- **Missing db.queries functions:** Need 7 new functions

---

## Implementation Checklist

### Phase 1: Fix update.py (Quick Wins)

**File:** `cli/update.py`

1. **Line 19:** `cache.get_companies()` → `cache.resolve_entities()`
   
   - Returns `Result[list[dict], str]`, need to unwrap with `is_ok()`

2. **Line 29:** `db.queries.select_missings()` → **IMPLEMENT THIS** (see below)

3. **Line 34:** `db.queries.select_role_mappings()` → **IMPLEMENT THIS**

4. **Line 49:** `db.queries.lookup_filing_row()` → **IMPLEMENT THIS**

5. **Line 54:** `cache.get_xbrl_url()` → `cache.resolve_xbrl_url()`
   
   - Returns `Result[str|None, str]`, need to unwrap

6. **Line 59:** `xbrl.arelle.get_model()` → `xbrl.arelle.load_model()`
   
   - Returns `Result[ModelXbrl, str]`, need to unwrap

7. **Line 64:** `xbrl.arelle.get_dei()` → `xbrl.arelle.extract_dei()`
   
   - Returns plain dict (no Result wrapper)

8. **Line 65:** `db.queries.update_dei()` → **IMPLEMENT THIS**

9. **Line 76:** `xbrl.arelle.presentation_facts()` → `xbrl.arelle.role_facts()`

10. **Line 79:** `xbrl.extract.is_consolidated()` → `xbrl.facts.is_consolidated()`

11. **Line 88:** `db.queries.insert_facts_with_roles()` → **IMPLEMENT THIS**

12. **Line 96:** `xbrl.extract.taxonomy_and_tag()` → `xbrl.facts.get_concept()`

13. **Line 97:** `db.queries.lookup_concept_id()` → **IMPLEMENT THIS**

14. **Line 100:** `db.queries.upsert_concept()` → **IMPLEMENT THIS**

15. **Line 101:** `xbrl.extract.fact_record()` → `xbrl.facts.make_record()`

16. **Line 112:** `r["concept_id"]` → `r["cid"]` (refactoring fix)

17. **Line 119:** `db.queries.existing_fact_modes()` → **IMPLEMENT THIS**

18. **Lines 124-130:** `xbrl.extract.q*_best_fact()` → `xbrl.facts.get_best_q*()`

### Phase 2: Implement Missing db.queries Functions

**File:** `db/queries.py`

#### 1. `select_missings(conn, cik) -> Result[list[dict], str]`

```python
"""
Find filings without facts for a company.
Returns list of filing dicts with access_no, filing_date, etc.

Query:
  SELECT f.* FROM filings f
  WHERE f.cik = ?
  AND NOT EXISTS (
    SELECT 1 FROM facts fa
    JOIN filing_roles fr ON fa.rid = fr.rid
    WHERE fr.access_no = f.access_no
  )
  ORDER BY f.filing_date
"""
```

#### 2. `select_role_mappings(conn, cik) -> dict[str, list[str]]`

```python
"""
Get role patterns for a company, grouped by group name.
Returns: {"Balance": ["StatementBalanceSheet", "BalanceSheetParenthetical"], ...}

Logic:
  1. Get all groups that have role patterns for this CIK
  2. For each group, get the role patterns
  3. Match patterns against filing_roles.name using LIKE
  4. Return dict of {group_name: [matched_role_names]}

Query involves:
  - groups
  - group_role_patterns
  - role_patterns (filter by cik, apply pattern matching)
  - filing_roles (get actual role names from filings)
"""
```

#### 3. `lookup_filing_row(conn, access_no) -> dict | None`

```python
"""
Get filing metadata by access number.
Returns dict with filing_date, ticker, cik, etc.

Query:
  SELECT f.*, e.ticker
  FROM filings f
  JOIN entities e ON f.cik = e.cik
  WHERE f.access_no = ?
"""
```

#### 4. `lookup_concept_id(conn, cik, taxonomy, tag) -> int | None`

```python
"""
Find concept ID by taxonomy and tag.
Returns cid or None if not found.

Query:
  SELECT cid FROM concepts
  WHERE cik = ? AND taxonomy = ? AND tag = ?
"""
```

#### 5. `upsert_concept(conn, cik, taxonomy, tag, name) -> int`

```python
"""
Insert concept if not exists, return cid.
Uses concept_insert_or_ignore() which already exists.
Returns the cid (either newly inserted or existing).
"""
```

#### 6. `update_dei(conn, dei_dict) -> Result[int, str]`

```python
"""
Insert or update DEI record for a filing.
Uses dei_insert_or_ignore() which already exists.

dei_dict contains:
  - access_no (required)
  - doc_type, doc_period_end, fiscal_year, fiscal_period, etc.
"""
```

#### 7. `existing_fact_modes(conn, cik, fiscal_year, concept_id, dimensions) -> list[dict]`

```python
"""
Get existing fact modes for a concept to help quarterly selection.
Returns: [{"mode": "quarter", "fiscal_period": "Q1"}, ...]

This is complex:
  1. Find facts matching: cik, fiscal_year, concept_id
  2. If dimensions provided, match those too
  3. Join with contexts to get mode
  4. Join with dei to get fiscal_period
  5. Return list of {mode, fiscal_period} for past facts

Query joins:
  - facts
  - filing_roles (to get access_no)
  - dei (to filter fiscal_year, get fiscal_period)
  - contexts (to get mode)
  - dimensions (if dimensions dict is not empty)
"""
```

#### 8. `insert_facts_with_roles(conn, facts_list) -> int`

```python
"""
Bulk insert facts with their dimensions and contexts.
Returns count of facts inserted.

For each fact record:
  1. Insert/get context (start_date, end_date, mode) -> xid
  2. Insert/get unit (unit name) -> unid
  3. Get rid from filing_roles (access_no + role)
  4. Insert fact (rid, cid, xid, unid, value) -> fid
  5. If dimensions exist, insert into dimensions table

fact record contains:
  - access_no
  - role
  - cid
  - value
  - start_date, end_date, mode
  - unit
  - dimensions (dict of {dim: member})
  - has_dimensions (bool)
"""
```

### Phase 3: Handle Result Types

**Important:** update.py was written before Result pattern. Need to:

- Unwrap Result types from cache functions
- Handle errors properly
- Add try/except around database operations

**Example pattern:**

```python
result = cache.resolve_entities(conn, [ticker])
if is_not_ok(result):
    print(f"Error: {result[1]}")
    return
entities = result[1]
```

### Phase 4: Test with AEO

**Commands:**

```bash
# Should import facts for filings that don't have them yet
ep update -t AEO

# Verify facts were imported
sqlite3 store.db "SELECT COUNT(*) FROM facts"
sqlite3 store.db "SELECT COUNT(*) FROM dimensions"

# Check a sample fact
sqlite3 store.db "
  SELECT f.fid, f.value, c.name, ctx.mode, u.name as unit
  FROM facts f
  JOIN concepts c ON f.cid = c.cid
  JOIN contexts ctx ON f.xid = ctx.xid
  JOIN units u ON f.unid = u.unid
  LIMIT 10
"
```

---

## Key Design Decisions

### 1. Store All Facts (Hybrid Approach)

- ✅ Import facts with AND without dimensions
- ✅ Mark with `has_dimensions` flag
- ✅ Store dimension details in separate table
- ✅ Future queries can filter on `has_dimensions = 0` for consolidated

### 2. Smart Quarterly Selection

- Keep the existing logic in `get_best_q1/q2/q3/fy()`
- This handles companies reporting in different ways:
  - Q2 as semester vs quarter
  - Q3 as 9-month YTD vs quarter
  - FY derivation

### 3. Role Pattern Matching

- Use existing group/pattern system
- Only extract facts from roles matching patterns
- This focuses on relevant financial statements

### 4. Incremental Updates

- Only process filings without facts (`select_missings`)
- Idempotent: can run multiple times safely

---

## Database Schema Reference

### Facts Storage

```sql
facts (fid, rid, cid, xid, unid, value)
  ↓
dimensions (fid, dimension, member)  -- Only if has_dimensions
```

### Supporting Tables

```sql
contexts (xid, start_date, end_date, mode)
units (unid, name)
filing_roles (rid, access_no, name)
concepts (cid, cik, taxonomy, tag, name)
dei (did, access_no, fiscal_year, fiscal_period, ...)
```

---

## Expected Behavior

**Input:** Filing with Balance Sheet role containing 50 concepts × 4 quarters
**Output:** ~200 facts inserted (50 concepts × 4 time periods)

**Consolidation:** Only facts with no dimensions stored initially
**Dimensions:** Table remains empty for now (can change filter later)

---

## Success Criteria

1. ✅ `ep update -t AEO` runs without errors
2. ✅ Facts table populated with consolidated data
3. ✅ Can query: "Show me Cash for AEO by quarter"
4. ✅ DEI data captured (fiscal periods correct)
5. ✅ Quarterly logic works (Q1, Q2, Q3, FY all present)
6. ✅ Idempotent (running twice doesn't duplicate)

---

## Notes for Implementation

- **Error handling:** Wrap in try/except, use Result pattern
- **Transactions:** Commit after each filing to avoid loss on error
- **Logging:** Print progress (filing date, facts inserted)
- **Testing:** Start with ONE filing, verify before batch
- **Validation:** Check contexts/units created correctly

---

## Future Enhancements (Not Now)

- [ ] Remove `is_consolidated()` filter to store dimensional facts
- [ ] Add queries for segment analysis
- [ ] Optimize bulk inserts (currently one at a time)
- [ ] Add fact update/correction logic
- [ ] Handle fact deletions from amended filings
