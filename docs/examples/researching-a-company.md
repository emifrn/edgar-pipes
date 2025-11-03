# Researching a Company with Edgar-Pipes

Step-by-step workflow for extracting financial data from SEC XBRL filings.

## Workflow Overview

1. **Probe** - Discover filings, roles, and concepts
2. **Define** - Create groups with role and concept patterns
3. **Update** - Extract facts into database
4. **Report** - Generate financial reports

## Step 1: Probe Filings

Fetch company filings from SEC:

```bash
ep probe filings -t AEO
```

Output: `cached 29 filings` (or similar). This discovers 10-K (annual) and 10-Q (quarterly) filings.

## Step 2: Probe Roles

Discover financial statement sections (roles) in the filings:

```bash
ep select filings -t AEO | ep probe roles
```

Caches all role names across all filings. Example roles:
- `StatementConsolidatedBalanceSheets`
- `StatementConsolidatedStatementsOfOperations`
- `StatementConsolidatedStatementsOfCashFlows`

## Step 3: Analyze Role Patterns

Role names vary across years. Find pattern variations:

```bash
ep select roles -t AEO | grep -i balance | sort -u
```

**AEO Balance Sheet example:**
- 2018: `StatementCONSOLIDATEDBALANCESHEETS`
- 2019-2021: `StatementConsolidatedBalanceSheets`
- 2022+ quarterly: `StatementConsolidatedBalanceSheets1`
- 2022+ annual: `Role_StatementConsolidatedBalanceSheets`
- Parenthetical: `StatementConsolidatedBalanceSheetsParenthetical`

**Create regex pattern:**
```regex
StatementConsolidatedBalanceSheets(1?|Parenthetical)|BALANCESHEETS(Parenthetical)?
```

Note: Use `|` for alternation, `?` for optional suffixes, no anchors needed.

## Step 4: Probe Concepts

Discover financial line items (concepts) within matched roles:

```bash
ep select filings -t AEO | ep select roles -p 'BALANCE_PATTERN' | ep probe concepts
```

Caches all concept tags found in balance sheet roles.

## Step 5: Define Groups and Patterns

### Create Group

```bash
ep new group Balance
```

### Create Role Pattern

```bash
ep new role -t AEO -n balance -p 'StatementConsolidatedBalanceSheets(1?|Parenthetical)|BALANCESHEETS(Parenthetical)?'
```

### Link Role to Group

```bash
ep add role -g Balance -t AEO -n balance
```

### Create Concept Patterns

Define patterns for each line item you want to track:

```bash
ep new concept -t AEO -u 1 -n 'Cash' -p '^CashAndCashEquivalentsAtCarryingValue$'
ep new concept -t AEO -u 2 -n 'Short term investments' -p '^ShortTermInvestments$'
ep new concept -t AEO -u 3 -n 'Inventory' -p '^InventoryNet$'
ep new concept -t AEO -u 4 -n 'Accounts receivable' -p '^AccountsReceivableNetCurrent$'
ep new concept -t AEO -u 5 -n 'Prepaid expense and other assets current' -p '^PrepaidExpenseAndOtherAssetsCurrent$'
ep new concept -t AEO -u 6 -n 'Current assets' -p '^AssetsCurrent$'
ep new concept -t AEO -u 7 -n 'Property plant and equipment' -p '^PropertyPlantAndEquipmentNet$'
ep new concept -t AEO -u 8 -n 'Total assets' -p '^Assets$'
# ... continue for all desired concepts
```

**Pattern tips:**
- Use `^TagName$` for exact match (most common)
- Use `^(TagA|TagB)$` for variations

**User IDs (-u, --uid):**
User-defined numeric identifiers for concepts. These act as shortcuts for easier reference:
- Allows referring to concepts by number instead of name
- Simplifies bulk operations: `ep add concept -g Balance -t AEO -u 1 2 3 4 5`
- Must be unique per ticker
- Use any numbering scheme (sequential recommended for organization)

### Link Concepts to Group

```bash
ep add concept -g Balance -t AEO -u 1 2 3 4 5 6 7 8
```

## Step 6: Update - Extract Facts

Fetch and store facts in database:

```bash
ep update -t AEO
```

Output shows progress per filing:
```
TICKER  CIK         ACCESS_NO             DATE        PERIOD   CAND  CHOS  INS
AEO     0000919012  0000950170-25-113811  2025-09-09  Q2 2025  1774    66    66
```

- **CAND** (candidates): All facts found matching role patterns
- **CHOS** (chosen): Facts selected after QTD/YTD logic
- **INS** (inserted): New facts inserted into database

## Step 7: Generate Reports

View extracted data:

```bash
# Table format (default when piped to terminal)
ep -t report -t AEO -g Balance

# Filter to quarterly data (Q1, Q2, Q3, Q4 - excludes YTD, FY)
ep report -t AEO -g Balance --quarterly

# Filter to annual data only (FY)
ep report -t AEO -g Balance --yearly

# Filter by date
ep report -t AEO -g Balance --after 2023-01-01

# Filter specific columns
ep report -t AEO -g Balance --cols Cash Inventory "Total assets"
```

## Understanding Report Modes

Reports show a `mode` column indicating measurement type:

- **instant**: Point-in-time snapshot (balance sheet items)
- **flow**: Period-based change (income statement, cash flow items)

**Q4 Derivation:**
- Stock variables (instant): Q4 = FY (same snapshot)
- Flow variables: Q4 = FY - 9M YTD (when 9M YTD exists)
- Flow variables: Q4 = FY - (Q1 + Q2 + Q3) (when all quarters exist)

**Why 9M YTD?**
Most companies report Q1 + **9M YTD** + FY for cash flow statements, not
individual Q2/Q3 quarters. The report shows "9M YTD" for these year-to-date
values.

## Hierarchical Groups

Create nested groups for detailed analysis:

```bash
ep new group Balance.Assets -t AEO --from Balance -u 1 2 3 4 5 6 7 8
ep new group Balance.Assets.Current -t AEO --from Balance -u 1 2 3 4 5 6
```

The `--from` flag copies role patterns from parent group, filtering to specified concept UIDs.

## Other Financial Statements

### Income Statement (Operations)

```bash
ep new group Operations
ep new role -t AEO -n operations -p '^(Role_)?Statement(CONSOLIDATEDSTATEMENTSOFOPERATIONS|ConsolidatedStatementsOfOperations)$'
ep add role -t AEO -g Operations -n operations

# Probe concepts
ep select roles -t AEO -g Operations | ep probe concepts

# Define concepts
ep new concept -t AEO -u 10 -n Revenue -p '^RevenueFromContractWithCustomerExcludingAssessedTax$'
ep new concept -t AEO -u 11 -n 'Cost of sales' -p '^CostOfGoodsAndServicesSold$'
ep new concept -t AEO -u 12 -n 'Gross profit' -p '^GrossProfit$'
ep new concept -t AEO -u 13 -n 'Operating income' -p '^OperatingIncomeLoss$'
ep new concept -t AEO -u 14 -n 'Net income' -p '^NetIncomeLoss$'
# ... more concepts

ep add concept -g Operations -t AEO -u 10 11 12 13 14
```

### Cash Flow Statement

```bash
ep new group CashFlow
ep new role -t AEO -n cashflow -p '^(Role_)?Statement(CONSOLIDATEDSTATEMENTSOFCASHFLOWS|ConsolidatedStatementsOfCashFlows)$'
ep add role -t AEO -g CashFlow -n cashflow

ep new concept -t AEO -u 20 -n 'Operating cash flow' -p '^NetCashProvidedByUsedInOperatingActivities$'
ep new concept -t AEO -u 21 -n 'Investing cash flow' -p '^NetCashProvidedByUsedInInvestingActivities$'
ep new concept -t AEO -u 22 -n 'Financing cash flow' -p '^NetCashProvidedByUsedInFinancingActivities$'
# ... more concepts

ep add concept -t AEO -g CashFlow -u 20 21 22
```

## Journal System

Record your workflow for reproducibility:

```bash
# Enable journal for specific company
ep journal use aeo

# Commands are automatically recorded
# Replay later:
ep journal replay

# Replay specific commands:
ep journal replay 1-50

# Disable recording:
ep journal off
```

## Common Issues

**Missing Q2/Q3 cash flow data:**
Normal. Many companies report Q1 (quarter) + 9M YTD + FY for cash flow, not individual Q2/Q3 quarters.

**Role names changing:**
Companies update XBRL structure over time. Patterns handle variations with alternation (`|`) and optional parts (`?`).

**Concept tag variations:**
Same financial item may use different tags across years. Use alternation to match both: `^(OldTag|NewTag)$`.
