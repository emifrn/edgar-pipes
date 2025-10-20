# Facts Import - Quick Checklist

Reference: See `facts_import_plan.md` for full details

## Implementation Order

### 1. Fix cli/update.py Imports & Function Names (18 changes)

- [ ] Line 19: `cache.get_companies()` → `cache.resolve_entities()` + unwrap Result
- [ ] Line 54: `cache.get_xbrl_url()` → `cache.resolve_xbrl_url()` + unwrap Result
- [ ] Line 59: `xbrl.arelle.get_model()` → `xbrl.arelle.load_model()` + unwrap Result
- [ ] Line 64: `xbrl.arelle.get_dei()` → `xbrl.arelle.extract_dei()` (no unwrap)
- [ ] Line 76: `xbrl.arelle.presentation_facts()` → `xbrl.arelle.role_facts()`
- [ ] Line 79: `xbrl.extract.is_consolidated()` → `xbrl.facts.is_consolidated()`
- [ ] Line 96: `xbrl.extract.taxonomy_and_tag()` → `xbrl.facts.get_concept()`
- [ ] Line 101: `xbrl.extract.fact_record()` → `xbrl.facts.make_record()`
- [ ] Line 112: `r["concept_id"]` → `r["cid"]`
- [ ] Lines 124-130: `xbrl.extract.*` → `xbrl.facts.get_best_*()`

### 2. Implement db.queries Functions (8 functions)

- [ ] `select_missings(conn, cik)` - Find filings without facts
- [ ] `select_role_mappings(conn, cik)` - Get role patterns
- [ ] `lookup_filing_row(conn, access_no)` - Get filing metadata
- [ ] `lookup_concept_id(conn, cik, taxonomy, tag)` - Find concept
- [ ] `upsert_concept(conn, cik, taxonomy, tag, name)` - Insert/get concept
- [ ] `update_dei(conn, dei_dict)` - Insert DEI data
- [ ] `existing_fact_modes(conn, cik, fiscal_year, cid, dims)` - Query for quarterly logic
- [ ] `insert_facts_with_roles(conn, facts_list)` - Bulk insert facts

### 3. Test & Verify

- [ ] Run: `ep update -t AEO`
- [ ] Check facts count: `SELECT COUNT(*) FROM facts`
- [ ] Verify quarterly data present: `SELECT DISTINCT fiscal_period FROM dei`
- [ ] Sample query works: Get Cash by quarter for AEO

## Critical Points

⚠️ **Result Type Handling:** Many functions return `Result[T, str]` - must unwrap with `is_ok()`
⚠️ **Column Names:** Use `cid`, `rid`, `xid`, `fid`, `unid` (not long forms)
⚠️ **Has Dimensions:** Check `has_dimensions` field exists in fact records

## Quick Test Query

```sql
-- After import, should see facts
SELECT
  c.name as concept,
  f.value,
  d.fiscal_period,
  ctx.mode
FROM facts f
JOIN concepts c ON f.cid = c.cid
JOIN filing_roles fr ON f.rid = fr.rid
JOIN dei d ON fr.access_no = d.access_no
JOIN contexts ctx ON f.xid = ctx.xid
WHERE c.cik = '0000919012'  -- AEO
LIMIT 20;
```

## Next Session Command

```
I need to implement the facts import functionality for the Edgar CLI.
Please reference: docs/facts_import_plan.md

Start by fixing cli/update.py function references, then implement the
missing db.queries functions. Follow the checklist in
docs/facts_import_checklist.md.
```
