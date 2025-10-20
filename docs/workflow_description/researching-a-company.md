# Researching a Company with the Edgar Tool

This guide explains how to systematically research a company using the `edgar` CLI tool, from initial discovery through creating repeatable analysis workflows.

## Overview

The ep tool extracts financial data from SEC XBRL filings. The general workflow is:

1. **Probe** - Discover and cache available filings, roles, and concepts
2. **Analyze** - Identify patterns in role names and concept tags across time
3. **Define** - Create groups with role and concept patterns
4. **Update** - Fetch facts for your defined groups
5. **Report** - Generate analysis reports

## Prerequisites

Before starting, ensure you have:
- A ticker symbol (e.g., "AEO" for American Eagle Outfitters)
- The company added to the database: `ep add -t TICKER`
- A journal to record your work: `ep journal use TICKER` (lowercase recommended)
- Journal recording enabled: `ep journal on`

## Step 1: Initial Discovery - Probe Filings

Start by discovering what filings are available:

```bash
ep probe filings -t TICKER
```

This fetches the company's recent filings from the SEC and caches them. You'll see output like:

```
[1/1] Fetching filings for AEO... cached 29 filings
```

**What to check:**
- How many years of data are available
- What form types exist (10-K annual, 10-Q quarterly)
- Filing date ranges

## Step 2: Discover Roles (Financial Statements)

Next, discover what XBRL roles (financial statements) exist in these filings:

```bash
ep select filings -t TICKER | ep probe roles
```

This caches all role names from all filings. Roles represent financial statement presentations like:
- Balance Sheets
- Income/Operations Statements
- Cash Flow Statements
- Stockholders' Equity Statements

## Step 3: Analyze Role Name Patterns

**Critical step:** Role names change over time as companies update their filing formats. You need to identify patterns.

### Find Balance Sheet Roles

```bash
ep select roles -t TICKER --cols role_name | grep -i balance | sort -u
```

**What you're looking for:**
- Different naming conventions across years
- Variations: `StatementConsolidatedBalanceSheets` vs `StatementCONSOLIDATEDBALANCESHEETS`
- Suffixes: `StatementConsolidatedBalanceSheets1` (10-Q) vs `Role_StatementConsolidatedBalanceSheets` (10-K)
- Parenthetical versions: `StatementConsolidatedBalanceSheetsParenthetical`

### Example Pattern Discovery

For AEO Balance Sheets, we found:
- 2018 Q: `StatementCONSOLIDATEDBALANCESHEETS`
- 2019-2021: `StatementConsolidatedBalanceSheets`
- 2022-2025 Q: `StatementConsolidatedBalanceSheets1`
- 2022-2025 K: `Role_StatementConsolidatedBalanceSheets`

### Create a Regex Pattern

Combine variations into a single regex:

```regex
^(Role_)?StatementConsolidatedBalanceSheets(1?|Parenthetical)$|^StatementCONSOLIDATEDBALANCESHEETS(Parenthetical)?$
```

**Pattern tips:**
- `^` and `$` for exact matches (prevents partial matches)
- `(Role_)?` for optional "Role_" prefix
- `1?` for optional "1" suffix
- `|` to combine completely different formats

### Verify Your Pattern

Test that your pattern matches all filings:

```bash
ep select roles -t TICKER -p 'YOUR_REGEX_PATTERN' --cols access_no filing_date form_type
```

Count matches and compare against total filings to ensure you haven't missed any.

## Step 4: Probe Concepts from Balance Sheet

Once you have the role pattern, discover what concepts (line items) are available:

```bash
ep select roles -t TICKER -p 'BALANCE_SHEET_PATTERN' | ep probe concepts
```

This will cache all concepts found in balance sheet roles across all filings.

## Step 5: Analyze Concept Patterns

Concepts also vary across time. Use SQL to analyze frequency:

```bash
sqlite3 store.db "
SELECT c.tag, COUNT(DISTINCT fr.access_no) as count
FROM filing_role_concepts frc
JOIN filing_roles fr ON frc.rid = fr.rid
JOIN concepts c ON frc.cid = c.cid
WHERE fr.name LIKE '%ConsolidatedBalanceSheet%'
GROUP BY c.tag
ORDER BY count DESC, c.tag
LIMIT 50;
"
```

**What to look for:**
- Concepts appearing in all/most filings (core items)
- Concepts with frequency changes (reporting changes)
- Variations of the same concept (e.g., `PrepaidExpenseAndOtherAssetsCurrent` vs `PrepaidExpenseCurrent`)

### Common Balance Sheet Concepts

**Assets:**
- Current: `CashAndCashEquivalentsAtCarryingValue`, `AccountsReceivableNetCurrent`, `InventoryNet`, `AssetsCurrent`
- Non-current: `PropertyPlantAndEquipmentNet`, `Goodwill`, `IntangibleAssetsNetExcludingGoodwill`, `OperatingLeaseRightOfUseAsset`
- Total: `Assets`

**Liabilities:**
- Current: `AccountsPayableCurrent`, `EmployeeRelatedLiabilitiesCurrent`, `OperatingLeaseLiabilityCurrent`, `LiabilitiesCurrent`
- Non-current: `LongTermDebtNoncurrent`, `OperatingLeaseLiabilityNoncurrent`, `LiabilitiesNoncurrent`

**Equity:**
- `CommonStockSharesOutstanding`, `AdditionalPaidInCapitalCommonStock`, `RetainedEarningsAccumulatedDeficit`, `TreasuryStockValue`, `StockholdersEquity`

## Step 6: Create Group and Patterns

Enable journal recording:

```bash
ep journal use TICKER
```

### Create the Group

```bash
ep new group Balance
```

### Create and Add Role Pattern

```bash
ep new role -t TICKER -u 1 -p 'YOUR_BALANCE_SHEET_REGEX'
ep add role -t TICKER -g Balance -u 1
```

**User ID guidelines:**
- Start with `u 1` for first role pattern
- Increment for additional patterns (if needed)

### Create Concept Patterns

For each line item you want to track:

```bash
ep new concept -t TICKER -u 1 -n 'Cash' -p '^CashAndCashEquivalentsAtCarryingValue$'
ep new concept -t TICKER -u 2 -n 'Inventory' -p '^InventoryNet$'
ep new concept -t TICKER -u 3 -n 'Total assets' -p '^Assets$'
# ... continue for all concepts
```

**Naming tips:**
- Use clear, business-friendly names (not XBRL tag names)
- Keep names concise for report readability
- Be consistent across companies for comparability

**Pattern tips:**
- Use exact match (`^TagName$`) when tags are consistent
- Use alternation for variations: `^(TagA|TagB)$`
- User IDs must be unique per ticker

### Add All Concepts to Group

```bash
ep add concept -g Balance -t TICKER -u 1 2 3 4 5 6 7 8 9 10
```

List all the user IDs you created.

## Step 7: Update - Fetch Facts

Now fetch the actual financial data:

```bash
ep update -t TICKER -g Balance
```

This:
1. Selects roles matching your Balance group pattern
2. Selects concepts matching your concept patterns
3. Fetches facts from SEC XBRL files for those role-concept combinations
4. Stores them in the database

**Expected output:**
```
TICKER  CIK         ACCESS_NO             DATE        PERIOD   CAND  CHOS  INS
  ...progress for each filing...
```

Or if already cached:
```
up to date (no filings without facts)
```

## Step 8: Generate Reports

View your analysis:

```bash
# JSON format (for piping to other commands)
ep report -t TICKER -g Balance

# Table format (human-readable)
ep -t report -t TICKER -g Balance

# Filter to recent periods
ep report -t TICKER -g Balance --after 2023-01-01

# Filter to quarterly data only (Q1, Q2, Q3, Q4 - excludes YTD and FY)
ep report -t TICKER -g Operations --quarterly

# Filter to annual data only (FY only)
ep report -t TICKER -g CashFlow --yearly

# Combine filters: quarterly data for specific columns
ep report -t TICKER -g Operations --quarterly --cols Revenue "Gross profit" "Net income"

# Calculate ratios
ep report -t TICKER -g Balance | calc "Current ratio = Current assets / Current liabilities"
```

### Understanding Period Labels in Reports

**CRITICAL:** Reports use **mode** to determine period labels, not just fiscal_period from the filing:

| Mode | Period Label | What It Means |
|------|-------------|---------------|
| `quarter` | Q1, Q2, Q3 | Standalone 3-month quarter |
| `semester` | 6M YTD | 6-month year-to-date (rare) |
| `threeQ` | **9M YTD** | **9-month year-to-date (NOT "Q3"!)** |
| `year` | FY | Full fiscal year |
| `instant` | Q1, Q2, Q3, FY | Point-in-time (balance sheet) |

**Why this matters:**
- Cash Flow statements often show Q1 + **9M YTD** + FY (not individual Q2/Q3)
- Income statements show Q1 + Q2 + Q3 + Q4 + FY (actual quarters)
- Without filters, you'll see BOTH "Q3" (quarter) AND "9M YTD" in the same report
- Use `--quarterly` to get consistent quarterly data for plotting

**Q4 Derivation:**
- If 9M YTD exists: `Q4 = FY - 9M YTD`
- If Q1, Q2, Q3 exist: `Q4 = FY - (Q1 + Q2 + Q3)`
- Balance sheet (instant): `Q4 = FY` (same snapshot)

## Step 9: Disable Journal Recording

Once you have a working setup, disable journal recording to avoid recording routine commands:

```bash
ep journal off
```

Re-enable when you want to record new setup commands:

```bash
ep journal on
```

Check the current recording state:

```bash
ep journal status
```

## Common Patterns and Best Practices

### Pattern Discovery Process

1. **Start broad, then narrow:**
   - First: `grep -i balance` to see all variations
   - Then: Group by year/form type to identify patterns
   - Finally: Create regex that captures all variations

2. **Test incrementally:**
   - Build pattern for one year
   - Verify it matches those filings
   - Expand to cover other years
   - Re-verify

3. **Count your matches:**
   ```bash
   ep select roles -t TICKER -p 'PATTERN' | wc -l
   ```
   Compare against total filings to ensure completeness.

### Handling Time Period Changes

Companies change their XBRL structure over time. Common changes:

- **Role name format changes:** Mixed case → UPPERCASE → Role_ prefix
- **Concept tag changes:** Broader tags → specific tags (or vice versa)
- **Statement combinations:** Separate statements → combined statements

**Strategy:** Use alternation in your patterns to capture both old and new formats.

**Example:**
```regex
^(Role_)?Statement(OLDFORMAT|NewFormat)(1?)$
```

### Concept Pattern Strategies

**For stable concepts** (appear in all filings with same tag):
```bash
-p '^ExactTagName$'
```

**For concepts with variations:**
```bash
-p '^(TagVariantA|TagVariantB)$'
```

**For mutually exclusive alternatives** (one or the other, never both):
```bash
-p '^(OlderTag|NewerTag)$'
```

### Organizing Concepts

Consider creating hierarchical groups for complex statements:

```bash
ep new group Balance.Assets -t TICKER --from Balance -u 1 2 3 4 5
ep new group Balance.Assets.Current -t TICKER --from Balance -u 1 2 3
ep new group Balance.Assets.NonCurrent -t TICKER --from Balance -u 4 5
```

This allows both detailed and summary analysis.

## Understanding XBRL Taxonomy Versions

**CRITICAL INSIGHT:** The same financial concept can have **different CIDs** (concept IDs) across years due to XBRL taxonomy version changes.

### What Are Taxonomy Versions?

Companies use different US-GAAP taxonomy versions based on when they file:
- Q1 2024 (filed May 2024) → uses us-gaap/2023
- Q2 2024 (filed August 2024) → uses us-gaap/2024
- Q3 2024 (filed November 2024) → uses us-gaap/2024

### Why This Matters

**The system handles this correctly**, but you should understand what's happening:

1. **Same tag, different IDs:**
   - `NetCashProvidedByUsedInOperatingActivities` in us-gaap/2023 → CID 786
   - `NetCashProvidedByUsedInOperatingActivities` in us-gaap/2024 → CID 746
   - They represent the SAME concept, just from different taxonomy years

2. **Tag-based matching:**
   - The update process matches concepts by **tag name**, not CID
   - This allows Q2 logic to find Q1 facts even when taxonomy versions differ
   - Example: Q2 semester fact selection can reference Q1 quarter facts

3. **When to worry:**
   - **DON'T worry:** Same tag across different taxonomy versions = same concept
   - **DO check:** If a tag gets deprecated and replaced with a new tag (rare)
   - **DO monitor:** Major accounting standard changes (e.g., ASC 606 revenue recognition)

### Example: Why Q2 Cash Flow Often Shows Gaps

Many companies (like AEO) **don't file complete cash flow statements for Q2**:

**What's actually in Q2 10-Q filings:**
- Income statement: Full Q2 quarter data ✓
- Balance sheet: Full Q2 snapshot ✓
- Cash flow: **Only partial data** (e.g., stock compensation, depreciation)

**Why:**
- Q1: Companies report 3-month quarter
- Q2: Companies report 3-month quarter (income stmt) but often **skip detailed cash flow**
- Q3: Companies report 9-month YTD (not Q3 quarter!)
- Q4: Derived from FY - 9M YTD

**Result in reports:**
```
2024 Q1    Operating CF: -8,216,000      ✓ Actual data
2024 Q2    Operating CF: None            ✗ Not filed
2024 Q3    Operating CF: None            ✗ Not filed (only partial data)
2024 9M YTD Operating CF: 284,343,000    ✓ Actual YTD data
2024 Q4    Operating CF: 296,367,000     ✓ Derived (FY - 9M YTD)
2024 FY    Operating CF: 580,710,000     ✓ Actual data
```

**This is normal!** Different financial statements have different filing requirements.

## Troubleshooting

### Pattern doesn't match any filings

**Diagnosis:**
```bash
ep select roles -t TICKER --cols role_name | grep -i KEYWORD
```

Look at actual role names and adjust your regex.

### Concept appears in some filings but not others

This is normal. Companies add/remove line items over time. Check frequency:

```bash
sqlite3 store.db "SELECT COUNT(*) FROM filing_role_concepts ..."
```

If a concept appears in <50% of filings, consider whether it's worth tracking.

### Update says "up to date" but report is empty

The concepts may exist but not match your patterns. Verify:

1. Concept patterns are added to the group: `ep group summary -g Balance`
2. Role pattern matches filings: `ep select roles -t TICKER -g Balance`
3. Concepts exist in those roles: `ep select roles -t TICKER -g Balance | ep select concepts`

### Report shows unexpected nulls

**This is normal and expected!** The report now shows ALL concept columns, even when data doesn't exist.

**Why you see None/null values:**

For **balance sheet** (instant/point-in-time) concepts:
- The concept doesn't exist in that filing
- The concept exists but in a different role (check parentheticals)
- Line item was added/removed in later years

For **income statement** (duration/flow) concepts:
- Nulls are common for quarterly vs annual reporting
- Companies report different levels of detail in Q vs FY filings

For **cash flow** concepts:
- Q2 and Q3 often have **very limited data** (see "Why Q2 Cash Flow Often Shows Gaps" above)
- This is normal filing behavior, not a bug

**Why this is better:**
- **Before:** Missing columns made it hard to know what data was available
- **Now:** All columns always shown, None indicates genuinely missing data
- **For plotting:** Consistent column structure across all periods

**Example - Cash Flow with gaps:**
```
         Q1      Q2      Q3      9M YTD  Q4      FY
OpsCF    -8.2M   None    None    284.3M  296.4M  580.7M
CapEx    36.2M   None    None    134.9M  87.6M   222.5M
Stock    14.8M   6.8M    9.9M    None    7.5M    39.0M
```

This is accurate - stock compensation IS reported quarterly, but operating cash flow is NOT.

## Example: Complete Balance Sheet Setup

Here's a complete example workflow:

```bash
# 1. Setup
ep add -t AEO
ep journal use aeo
ep journal on

# 2. Discover
ep probe filings -t AEO
ep select filings -t AEO | ep probe roles

# 3. Analyze role patterns
ep select roles -t AEO --cols role_name | grep -i balance | sort -u

# 4. Probe concepts
ep select roles -t AEO -p '^(Role_)?StatementConsolidatedBalanceSheets(1?|Parenthetical)$|^StatementCONSOLIDATEDBALANCESHEETS(Parenthetical)?$' | ep probe concepts

# 5. Create group and patterns
ep new group Balance
ep new role -t AEO -u 1 -p '^(Role_)?StatementConsolidatedBalanceSheets(1?|Parenthetical)$|^StatementCONSOLIDATEDBALANCESHEETS(Parenthetical)?$'
ep add role -t AEO -g Balance -u 1

# 6. Create concepts (abbreviated)
ep new concept -t AEO -u 1 -n 'Cash' -p '^CashAndCashEquivalentsAtCarryingValue$'
ep new concept -t AEO -u 2 -n 'Inventory' -p '^InventoryNet$'
ep new concept -t AEO -u 3 -n 'Current assets' -p '^AssetsCurrent$'
ep new concept -t AEO -u 4 -n 'Total assets' -p '^Assets$'
# ... more concepts ...

ep add concept -g Balance -t AEO -u 1 2 3 4 5 6 7 8

# 7. Update and report
ep update -t AEO -g Balance
ep report -t AEO -g Balance

# 8. Disable journal recording
ep journal off
```

## Next Steps: Other Financial Statements

Once you have Balance working, apply the same process to:

### Operations/Income Statement

**Look for:** Roles containing "Operations", "Income", "Earnings"

**Key concepts:**
- Revenue: `Revenues`, `SalesRevenueNet`
- Costs: `CostOfGoodsAndServicesSold`, `OperatingExpenses`
- Income: `OperatingIncomeLoss`, `NetIncomeLoss`
- Per share: `EarningsPerShareBasic`, `EarningsPerShareDiluted`

### Stockholders' Equity Statement

**Look for:** Roles containing "StockholdersEquity", "ShareholdersEquity"

**Key concepts:**
- Changes: `NetIncomeLoss`, `DividendsCommonStock`, `StockIssuedDuringPeriodValueShareBasedCompensation`
- Repurchases: `TreasuryStockValueAcquiredCostMethod`
- Balances: `StockholdersEquity`, `CommonStockSharesOutstanding`

### Cash Flow Statement

**Look for:** Roles containing "CashFlow"

**Key concepts:**
- Operating: `NetCashProvidedByUsedInOperatingActivities`
- Investing: `NetCashProvidedByUsedInInvestingActivities`
- Financing: `NetCashProvidedByUsedInFinancingActivities`

## Best Practices for Data Analysis

### For Plotting and Visualization

**Use period filters for consistent data:**

```bash
# Quarterly trend analysis (avoids mixing quarter and YTD data)
ep report -t TICKER -g Operations --quarterly | plot-line

# Year-over-year comparison
ep report -t TICKER -g CashFlow --yearly | plot-bar

# Specific metrics only
ep report -t TICKER -g Operations --quarterly \
  --cols Revenue "Gross profit" "Operating income" | plot-trend
```

**Why filters matter:**
- Without `--quarterly`: You'll get Q1, Q2, Q3, **9M YTD**, Q4, FY (6 periods)
- With `--quarterly`: You'll get Q1, Q2, Q3, Q4 (4 consistent periods)
- **9M YTD ≠ Q3 quarter!** Don't plot them together

### Handling Missing Data in Analysis

**CSV export with gaps:**
```bash
ep --csv report -t TICKER -g CashFlow --quarterly > cashflow.csv
```

The CSV will include ALL columns, with empty cells for missing data. This is correct and useful:
- Spreadsheet tools handle empty cells gracefully
- Plotting tools can show gaps in line charts
- You can clearly see which metrics are consistently reported

**Understanding data completeness:**
```bash
# Check what data exists for a specific concept
ep report -t TICKER -g CashFlow --cols "Operating cash flow"
```

If many periods show None, that concept may not be consistently filed.

### Working with Mixed Period Types

**Income Statement** (always quarterly):
```bash
ep report -t TICKER -g Operations --quarterly
# Gives clean Q1, Q2, Q3, Q4 structure
```

**Cash Flow Statement** (mixed YTD and quarterly):
```bash
# For quarterly comparison (with gaps)
ep report -t TICKER -g CashFlow --quarterly

# For YTD analysis (includes 9M YTD)
ep report -t TICKER -g CashFlow
```

**Balance Sheet** (point-in-time, all periods available):
```bash
ep report -t TICKER -g Balance --quarterly
# Q1-Q4 snapshots for trend analysis
```

### Calculating Quarterly Estimates

When Q2/Q3 standalone data doesn't exist, you can estimate:

```python
# Get the data
import json, subprocess
data = json.loads(subprocess.run(
    ["edgar", "report", "-t", "AEO", "-g", "CashFlow"],
    capture_output=True, text=True
).stdout)

# Find Q1, 9M YTD, FY for a specific year
for row in data['data']:
    if row['fiscal_year'] == '2024':
        if row['fiscal_period'] == 'Q1':
            q1 = row['Operating cash flow']
        elif row['fiscal_period'] == '9M YTD':
            ytd_9m = row['Operating cash flow']
        elif row['fiscal_period'] == 'FY':
            fy = row['Operating cash flow']

# Estimate Q2+Q3 combined and Q4
q2_plus_q3 = ytd_9m - q1  # 6-month combined
q4 = fy - ytd_9m           # Already in report, but for reference

print(f"Q1: {q1}")
print(f"Q2+Q3 (combined): {q2_plus_q3}")
print(f"Q4: {q4}")
print(f"FY: {fy}")
```

**Note:** You cannot separate Q2 from Q3 without additional data.

## Advanced: Multi-Company Analysis

Once you have patterns working for one company, you can:

1. **Apply to competitors:** Same industry often uses similar XBRL patterns
2. **Compare across companies:** `ep report -t TICK1 TICK2 -g Balance`
3. **Build ratio libraries:** Create reusable calc expressions for your sector
4. **Use consistent filters:** Apply `--quarterly` across all companies for apples-to-apples comparison

## Summary Checklist

- [ ] Company added to database
- [ ] Journal created and recording enabled (`ep journal use TICKER && ep journal on`)
- [ ] Filings probed and cached
- [ ] Roles probed and patterns identified
- [ ] Concepts probed and analyzed
- [ ] Group created
- [ ] Role pattern created and linked
- [ ] Concept patterns created and linked
- [ ] Update run successfully
- [ ] Report generates expected data
- [ ] Journal recording disabled (`ep journal off`)

## Additional Resources

- **XBRL Taxonomy:** https://www.sec.gov/structureddata/osd-inline-xbrl.html
- **XBRL US GAAP:** https://xbrl.us/home/filers/sec-reporting/
- **Edgar Tool Docs:** Check the `docs/` folder for command-specific documentation

---

**Remember:** The key to successful company research is systematic discovery, pattern recognition, and verification. Take time in the analysis phase to ensure your patterns are comprehensive before creating your groups.
