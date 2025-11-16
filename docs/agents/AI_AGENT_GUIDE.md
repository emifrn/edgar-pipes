# AI Agent guide for edgar-pipes

A guide for AI agents analyzing financial data with edgar-pipes. This document
complements the [CHEATSHEET.md](../CHEATSHEET.md) and [README.md](../README.md)
with AI-specific guidance on progressive discovery, validation, and
interpretation.

## Core principles

### 1. Progressive discovery, not assumptions

Financial data varies significantly across companies and time periods. Never assume:

- Tag names are consistent across companies or years
- Metrics appear in all filings
- Patterns that work for one company work for another
- Accounting standards remain static

Always verify before creating patterns. Discovery first, pattern creation
second.

### 2. Validate across historical filings

The `-m` flag is your validation tool. Before creating any concept pattern:

```bash
# Check for missing coverage (gaps in data)
ep select filings -t TICKER | ep select roles -g GROUP | ep select concepts -p 'PATTERN' -m
```

* Empty result = full coverage. Non-empty result = pattern needs refinement or
  concept doesn't appear consistently.
* Exclude parenthetical roles when checking main balance sheet concepts:

```bash
... | ep select concepts -p 'PATTERN' -m | grep -v Parenthetical
```

Parenthetical roles contain supplemental disclosures (share counts, par
values). Gaps there are expected for main balance sheet line items.

### 3. Accuracy over convenience

You're reconstructing how a company reported itself over time. Inconsistencies
aren't errors—they're history:

* Accounting standard changes (ASC 842 leases, ASC 606 revenue)
* Metric definitions evolve
* Taxonomy versions differ
* Business model shifts affect reporting

Document these in concept notes. Don't try to smooth over discontinuities.

### 4. Maintain journals for reproducibility

**Journals are recipes, not logs.** Record only the minimal commands needed to
recreate the database from scratch, not the discovery process.

**DO journal (creation commands):**

```bash
ep -j probe filings -t TICKER          # Initial data fetch
ep -j new role -t TICKER -n name -p 'PATTERN'
ep -j new group GroupName
ep -j add role -g GroupName -t TICKER -n name
ep -j new concept -t TICKER -u 1 -n "Name" -p 'PATTERN'
ep -j add concept -g GroupName -t TICKER -u 1 2 3
ep -j new group Subgroup --from Parent -t TICKER -u 1 2
ep -j update -t TICKER -g GroupName     # Final extraction
```

**DO NOT journal (discovery/query commands):**

```bash
# These are for exploration only - don't clutter journals
ep select filings -t TICKER | probe roles
ep select concepts -p '(?i)cash' -c tag -u
ep select concepts -p 'PATTERN' -m
ep report -t TICKER -g GroupName --yearly
ep stats concepts -t TICKER -g GroupName
```

**Critical journal practices:**

- Use **progressive UIDs** (1, 2, 3...) for all concepts in sequential order
- Include **only creation commands** needed to recreate the database from scratch
- Omit all discovery, exploration, and query commands (`select`, `report`, `stats`)
- Test journal reproducibility by deleting `store.db` and running `ep journal replay`
- Keep journal synchronized with database state after making changes
- Think: "minimal recipe" not "complete history"

**Why journals matter:**

- Databases are large and binary; journals are compact text files
- Journals serve as templates for analyzing similar companies
- Sharing journals enables reproducible financial analysis
- Journals can be versioned, reviewed, and audited
- You can replay portions of journals for incremental updates

If you modify patterns or group membership outside of journal recording, always
update the journal afterward to maintain synchronization. The goal: anyone should
be able to recreate your exact database by replaying your journal.

## Workflow

### Discovery phase

**1. Understand what exists before creating anything**

```bash
# Discover available filings
ep probe filings -t TICKER

# Explore role names (financial statement sections)
ep select filings -t TICKER | ep probe roles

# Find role patterns by filtering
ep select filings -t TICKER | ep select roles -p '(?i)balance' -c role_name -u
```

**2. Test patterns before committing**

Refine role patterns until they match consistently across all filings. Use
case-insensitive regex `(?i)` when companies change naming conventions
(CamelCase → UPPERCASE).

**3. Probe concepts after roles are stable**

```bash
# Import concepts from matched roles
ep select filings -t TICKER | ep select roles -g GROUP | ep probe concepts

# Inspect available tags
ep select filings -t TICKER | ep select roles -g GROUP | ep select concepts -c tag -u
```

### Pattern creation

**4. Search for specific concepts**

```bash
# Find tag variations for a metric (e.g., cash, inventory, revenue)
ep select filings -t TICKER | ep select roles -g GROUP | ep select concepts -p '(?i)cash' -c tag -u
```

**5. Verify coverage with `-m` flag**

```bash
# Check if pattern matches across all filings
ep select filings -t TICKER | ep select roles -g GROUP | ep select concepts -p '^CashAndCashEquivalents.*$' -m | grep -v Parenthetical
```

If empty: Pattern has full coverage. Proceed to create concept.
If non-empty: Pattern missing in those filings. Refine pattern or document as adoption-dependent.

**6. Create concept only after verification**

```bash
# Create with semantic name, pattern, and user ID
ep new concept -t TICKER -n "Cash" -p '^CashAndCashEquivalents.*$' -u 1

# Link to group
ep add concept -g GROUP -t TICKER -u 1
```

### Group design

Create hierarchical groups:

**Master group** (`Balance`): All concepts, comprehensive view
**Detail groups** (`Balance.Assets.Current`): Focused slices of related line items
**Summary groups** (`Balance.Summary`): 3-6 headline totals only

Use `--from` to derive groups from parent. Never duplicate data.

```bash
# Derive subgroup with filtered concepts
ep new group Balance.Assets.Current --from Balance -t TICKER -u 1 2 3 4 5
```

### Updates and reporting

**7. Update database to extract facts**

```bash
# Initial extraction
ep update -t TICKER -g GROUP

# Updates propagate from parent groups to derived groups
# No need to update each subgroup separately
```

**8. Generate reports and validate**

```bash
# Check data makes sense
ep report -t TICKER -g GROUP --yearly

# Verify totals reconcile
# Example: Assets.Current should sum to individual current asset line items
```

## Concept naming convention

* Use hierarchical dot notation: `Category.Type.Period`
* Use CamelCase notation for multi-word names

**Hierarchy levels:**

1. **Category**: Assets, Liabilities, Equity, Operations, CashFlow
2. **Type**: Cash, Investments, PPE, Receivables, Payables, Accrued, Lease
3. **Period/State**: Current, Noncurrent, Net, Gross, Total

**Examples:**

* `Cash` - primary metric
* `Cash.Total` - comprehensive variant
* `Cash.Unrestricted` - historical variant
* `Investments.Current` - short-term marketable securities
* `Investments.Noncurrent` - long-term marketable securities
* `PPE.Net` - property, plant & equipment after depreciation
* `PPE.Gross` - before depreciation
* `PPE.Depreciation` - accumulated depreciation
* `Lease.RightsOfUse` - ASC 842 lease assets
* `Lease.Obligation.Current` - current lease liabilities
* `Assets.Current` - summary total
* `Liabilities.Total` - complete total

**Guidelines:**

* Choose names accountants would recognize
* Maintain consistent structure across the schema
* Document exceptional cases in notes
* Keep names concise

## AI-specific guidance

### When to ask questions

Ask the user when:

* Multiple valid interpretation approaches exist
* Ambiguity in data requires domain expertise
* Industry-specific accounting practices apply
* Detected opportunities, variations or semantic shifts
* Data inconsistencies or incomplete coverage

### Cross-validation strategies

1. **Check totals reconcile**: `Assets = Liabilities + Equity`
2. **Verify component sums**: Current assets should sum to total current assets
3. **Look for discontinuities**: Sudden jumps may indicate accounting changes
4. **Compare quarterly vs annual**: Should be consistent in definition

### Journal maintenance workflow

When working with users on company analysis:

**During initial setup:**

1. Explore freely without `-j` flag during discovery (select, probe concepts, stats)
2. Once patterns are finalized, use `-j` only for creation commands
3. Assign UIDs sequentially (1, 2, 3...) as you create concepts
4. Journal only: `probe filings` → `new role/group/concept` → `add` → `update`

**When modifying existing work:**

1. If patterns or groups were created without `-j`, reconstruct the journal
2. Remove any discovery commands from journal (select, report, stats)
3. Ensure UIDs are progressive and consistent with database state
4. Test reproducibility: `rm store.db && ep journal replay`
5. Keep journal as minimal recipe, not complete command history

**Journal quality checklist:**

- [ ] All UIDs are sequential (no gaps, no reuse)
- [ ] All groups are created with correct UID references
- [ ] Role patterns are included before being linked to groups
- [ ] Final `update` command is included
- [ ] Journal replay creates identical database

Journals are how you share analytical work—not databases. Always ensure journals
are complete and reproducible.

### Documentation standards

Keep notes **compact and significant**:

* One-liners only
* Record accounting standard changes with adoption dates
* Note timing of metric introductions
* Flag semantic shifts

**Good examples:**

```
--note 'ASC 842 adoption 2019-06-13; zero pre-adoption'
--note 'Aggregate pattern; handles 2020 metric transition'
--note 'Liquid cash only; used 2015-2020; superseded by Cash.Total'
```

## Additional resources

- **[README.md](../README.md)**: Full system overview and concepts
- **[CHEATSHEET.md](../CHEATSHEET.md)**: Quick command reference
- **[Architecture](developers/architecture.md)**: System design for contributors
- **[Examples](examples/)**: Sample workflows and journal files

For issues or questions: [GitHub Issues](https://github.com/emifrn/edgar-pipes/issues)
