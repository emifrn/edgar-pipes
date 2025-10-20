# XBRL Roles and Visual Presentation Structure

## Core Concept

What appears as a single financial statement on SEC.gov is actually **multiple XBRL roles combined** during HTML rendering. Edgar must capture ALL related roles to get complete data coverage.

## Visual vs. XBRL Structure

### What You See (SEC Viewer)

```
CONSOLIDATED BALANCE SHEET
─────────────────────────────────────────
Assets
  Current assets                    $XXX
  Property and equipment            $XXX

Liabilities and Stockholders' Equity  
  Accounts payable                  $XXX
  Preferred stock, $0.01 par value;
    5,000 shares authorized; 
    none issued                     $  -
  Common stock, $0.01 par value     $XXX
```

### What Exists in XBRL (Multiple Roles)

```
Role 1: StatementConsolidatedBalanceSheets1
  ├── AssetsCurrent = XXX
  ├── PropertyPlantAndEquipmentNet = XXX
  ├── AccountsPayable = XXX
  ├── PreferredStockValue = [empty]
  └── CommonStockValue = XXX

Role 2: StatementConsolidatedBalanceSheetsParenthetical
  ├── PreferredStockParOrStatedValuePerShare = 0.01
  ├── PreferredStockSharesAuthorized = 5,000,000
  ├── PreferredStockSharesIssued = 0
  ├── CommonStockParOrStatedValuePerShare = 0.01
  └── CommonStockSharesAuthorized = 600,000,000
```

## Role Types in XBRL

### Primary Roles

Contain the main numeric facts that appear in statement columns.

**Examples:**

- `StatementConsolidatedBalanceSheets`
- `StatementOfIncome`
- `StatementOfCashFlows`

### Parenthetical Roles

Contain descriptive details shown as inline notes within the statement.

**Pattern:** Usually same name + "Parenthetical" suffix

**Examples:**

- `StatementConsolidatedBalanceSheetsParenthetical`
- `StatementOfIncomeParenthetical`
- `StatementOfCashFlowsParenthetical`

**Common parenthetical facts:**

- Par values of stock
- Shares authorized/issued/outstanding
- Interest rates
- Maturity dates
- Useful lives of assets

### Detail/Schedule Roles

Contain supporting tables referenced from the main statement.

**Examples:**

- `EquityScheduleOfStockByClassTable`
- `PropertyPlantAndEquipmentSchedule`
- `DebtSchedule`

## Role Families by Statement Type

### Balance Sheet Family

```
Primary:
  - StatementConsolidatedBalanceSheets
  - StatementConsolidatedBalanceSheets1
  - StatementCONSOLIDATEDBALANCESHEETS (older filings)

Parenthetical:
  - StatementConsolidatedBalanceSheetsParenthetical

Related Details:
  - EquityScheduleOfStockByClassTable
  - PropertyPlantAndEquipmentSchedule
  - DebtSchedule
```

### Income Statement Family

```
Primary:
  - StatementOfIncome
  - StatementConsolidatedIncomeStatement

Parenthetical:
  - StatementOfIncomeParenthetical

Related Details:
  - EarningsPerShareSchedule
  - RevenueFromContractWithCustomerSchedule
```

### Cash Flow Family

```
Primary:
  - StatementOfCashFlows
  - StatementConsolidatedCashFlows

Parenthetical:
  - StatementOfCashFlowsParenthetical

Related Details:
  - ScheduleOfNonCashInvestingAndFinancingActivities
```

## Temporal Role Variations

Companies frequently change role naming conventions across filing periods:

**Example from AEO:**

```
2025: StatementConsolidatedBalanceSheets1
2024: StatementConsolidatedBalanceSheets1  
2023: Role_StatementConsolidatedBalanceSheets
2021: StatementCONSOLIDATEDBALANCESHEETS
2019: StatementConsolidatedBalanceSheets
```

**Causes:**

- XBRL consultant changes
- Filing software updates
- Taxonomy restructuring
- Company mergers/rebranding

## Pattern Strategy for Complete Coverage

### Incomplete Pattern (Misses Data)

```bash
# Only captures one specific role variant
ep add roles -t AEO -g Balance \
  --pattern '^StatementConsolidatedBalanceSheets1$'
```

**Problem:** Misses parenthetical role and historical variants

### Complete Pattern (Comprehensive)

```bash
# Captures entire role family
ep add roles -t AEO -g Balance \
  --pattern '.*[Bb]alance[Ss]heet.*'
```

**Captures:**

- StatementConsolidatedBalanceSheets
- StatementConsolidatedBalanceSheets1
- StatementConsolidatedBalanceSheetsParenthetical
- StatementCONSOLIDATEDBALANCESHEETS
- Role_StatementConsolidatedBalanceSheets

## Discovery Workflow for Complete Coverage

### Step 1: Identify Role Families

```bash
# Probe one recent filing to see available roles
ep select filings -t AEO --limit 1 | probe roles --list

# Filter to balance-sheet-related roles
ep select roles -t AEO | grep -i balance
```

### Step 2: Observe Role Naming Patterns

Look for:

- Primary statement roles
- Parenthetical variants (same name + Parenthetical)
- Related schedules/tables
- Historical naming variations

### Step 3: Build Comprehensive Patterns

```bash
# Pattern that captures role family
ep add roles -t AEO -g Balance \
  --pattern '.*[Bb]alance[Ss]heet.*'

# Verify what roles matched
ep select patterns -t AEO -g Balance --type roles
```

### Step 4: Verify Coverage

```bash
# See all matched roles across filings
ep select roles -t AEO -g Balance

# Should show:
# - Primary statement roles
# - Parenthetical roles
# - Related schedules
```

### Step 5: Probe Concepts from Complete Set

```bash
# Cache concepts from ALL matched roles
ep select roles -t AEO -g Balance | probe concepts
```

## Common Pattern Recipes

### Balance Sheet (Comprehensive)

```bash
ep add roles -t TICKER -g Balance \
  --pattern '.*[Bb]alance[Ss]heet.*|.*BALANCESHEET.*'
```

### Income Statement (Comprehensive)

```bash
ep add roles -t TICKER -g Income \
  --pattern '.*[Ii]ncome.*|.*[Oo]peration.*|.*INCOME.*'
```

### Cash Flow (Comprehensive)

```bash
ep add roles -t TICKER -g Cash \
  --pattern '.*[Cc]ash[Ff]low.*|.*CASHFLOW.*'
```

### Equity Details (Comprehensive)

```bash
ep add roles -t TICKER -g Equity \
  --pattern '.*[Ee]quity.*|.*[Ss]tock.*'
```

## Key Insights

1. **One visual statement = Multiple XBRL roles**
   
   - Main statement role
   - Parenthetical role
   - Supporting schedules

2. **Parenthetical roles contain critical details**
   
   - Stock par values
   - Shares authorized/issued
   - Descriptive information

3. **Role names evolve over time**
   
   - Pattern matching must handle variations
   - Use broad patterns with case-insensitive matching

4. **Complete coverage requires role families**
   
   - Don't just match the primary statement
   - Include parenthetical and related schedules

5. **Missing a role = Missing concepts**
   
   - If concepts seem absent, check role coverage
   - Probe all roles in the family

## Diagnostic Commands

### Check Current Role Coverage

```bash
# What roles does your group match?
ep select roles -t TICKER -g GROUP_NAME

# Are parenthetical roles included?
ep select roles -t TICKER -g GROUP_NAME | grep -i parenthetical
```

### Find Missing Roles

```bash
# See all available roles for a filing
ep select filings -t TICKER --limit 1 | probe roles --list

# Compare to your group's matches
ep select roles -t TICKER -g GROUP_NAME
```

### Test Pattern Coverage

```bash
# Add pattern and verify immediately
ep add roles -t TICKER -g GROUP_NAME --pattern 'PATTERN'
ep select roles -t TICKER -g GROUP_NAME
```

## Real-World Example: PreferredStock Discovery

**Initial pattern:** `StatementConsolidatedBalanceSheets1`

- Captured: Main balance sheet line items
- Missed: Stock par values (in Parenthetical role)

**Enhanced pattern:** `.*[Bb]alance[Ss]heet.*`

- Captured: Main statement + Parenthetical role
- Found: PreferredStockParOrStatedValuePerShare = 0.01

**Lesson:** Broad patterns capture complete statement families, narrow patterns miss critical details.
