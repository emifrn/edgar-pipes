# Edgar Groups, Roles, and Concepts: Complete Guide

## Core Architecture

### Entity Hierarchy

```
Companies (CIK + Ticker) 
    ↓
XBRL Filings (10-K, 10-Q)
    ↓  
XBRL Roles ("StatementConsolidatedBalanceSheets", "StatementOfIncome")
    ↓
XBRL Concepts ("CashAndCashEquivalentsAtCarryingValue", "Revenue")
    ↓
Financial Facts (numerical values with periods)
```

### Pattern System

```
Groups (Global semantic containers)
    ↓ Many-to-Many
Role Patterns (Where to look) + Concept Patterns (What to extract)
    ↓ Company-specific (CIK)
Pattern Definitions (Regex expressions)
```

## Database Schema

### Groups: Global Semantic Containers

```sql
groups (group_id, name)
```

- Semantic organization ("balance", "income", "assets")
- Global scope (not tied to specific companies)

### Role Patterns: "Where to Look"

```sql
role_patterns (pattern_id, cik, pattern)
group_role_patterns (group_id, pattern_id)  -- Many-to-Many
```

- Define which XBRL roles contain relevant data
- Company-specific patterns for same group

### Concept Patterns: "What to Extract"

```sql
concept_patterns (pattern_id, cik, name, pattern)
group_concept_patterns (group_id, pattern_id)  -- Many-to-Many
```

- Define which financial concepts to extract
- Company-specific with semantic names

## Key Concepts

### Groups as Abstract Pointers

Groups point to role patterns (where to look) and concept patterns (what to extract), filtered by company.

### Company-Specific Materialization

```
Group "balance" for AAPL:
- Role patterns: ["StatementConsolidatedBalanceSheets.*"]  
- Concept patterns: ["Cash": "^CashAndCash.*", "Inventory": "^Inventory.*"]

Group "balance" for MSFT:  
- Role patterns: ["BalanceSheet.*"]
- Concept patterns: ["Cash": "^CashEquivalents.*", "Inventory": "^InventoryNet.*"]
```

## CLI Commands

### 1. Group Management

**Create Groups:**

```bash
# Emedgar new "current_assets" --ticker AAPL --from "balance" --pattern ".*Assets.*" --exclude ".*Noncurrent.*"pty group
ep new balance --ticker AAPL

# Derived group (copies role and concept patterns)

```

**List and Delete:**

```bash
ep select groups
ep select groups --name "balance"
ep select groups --name "old_group" | delete --yes
```

### 2. Role Pattern Management

**Create New Pattern:**

```bash
ep add role --ticker AAPL --group balance --pattern 'StatementConsolidatedBalanceSheets.*'
```

**Link Existing Pattern:**

```bash
# Link single pattern
ep add role --group balance --id 15

# Link multiple patterns (including cross-company)
ep add role --group tech_income --id 15 42 87
```

**View Patterns:**

```bash
ep select patterns --ticker AAPL --group balance --type roles
```

### 3. Concept Pattern Management

**Create New Pattern:**

```bash
ep add concept --ticker AAPL --group balance --name "Cash" --pattern '^CashAndCash.*$'
```

**Link Existing Pattern:**

```bash
# Link single pattern
ep add concept --group balance --id 23

# Link multiple patterns across companies
ep add concept --group cash_comparison --id 23 45 91
```

**View Patterns:**

```bash
ep select patterns --ticker AAPL --group balance --type concepts
```

### 4. Data Discovery and Extraction

**Concept Discovery:**

```bash
# Using group patterns
ep select concepts --ticker AAPL --group balance --name "Cash"

# With additional filtering
ep select concepts --ticker AAPL --group balance --pattern ".*Current.*"
```

**Extract Financial Data:**

```bash
# Specific concept
ep update --ticker AAPL --group balance --name "Cash"

# Entire group
ep update --ticker AAPL --group balance
```

## Workflow Examples

### Building a Balance Sheet Group

```bash
# 1. Create group and add role patterns
ep new balance --ticker AAPL
ep add role --ticker AAPL --group balance --pattern 'StatementConsolidatedBalanceSheets.*'

# 2. Add concept patterns
ep add concept --ticker AAPL --group balance --name "Cash" --pattern '^CashAndCash.*$'
ep add concept --ticker AAPL --group balance --name "Inventory" --pattern '^InventoryNet$'

# 3. Verify configuration
ep select patterns --ticker AAPL --group balance

# 4. Test discovery
ep select concepts --ticker AAPL --group balance
```

### Creating Specialized Groups

```bash
# Derive from comprehensive group
ep new "current_assets" --ticker AAPL --from "balance" --names "Cash|Inventory|Receivables"

# Verify patterns copied
ep select patterns --ticker AAPL --group "current_assets"
```

### Cross-Company Pattern Reuse

```bash
# Build patterns for first company
ep new balance --ticker AAPL
ep add role --ticker AAPL --group balance --pattern 'StatementConsolidatedBalanceSheets.*'
ep add concept --ticker AAPL --group balance --name "Cash" --pattern '^CashAndCash.*$'

# Reuse patterns for another company
ep new balance --ticker MSFT
ep add role --ticker MSFT --group balance --pattern 'BalanceSheet.*'

# Link existing concept pattern from AAPL to MSFT's balance group
ep select patterns --ticker AAPL --group balance --type concepts  # Note pattern ID
ep add concept --group balance --id 23  # Link AAPL's cash pattern to MSFT's group
```

### Cross-Company Analysis Groups

```bash
# Create group for comparing cash across tech companies
ep new "tech_cash" --ticker AAPL

# Add patterns from multiple companies
ep add concept --ticker AAPL --group "tech_cash" --name "Cash" --pattern '^CashAndCash.*$'
ep add concept --ticker MSFT --group "tech_cash" --name "Cash" --pattern '^CashEquivalents.*$'

# Or link existing patterns by ID
ep add concept --group "tech_cash" --id 23 45 91  # AAPL, MSFT, GOOGL patterns
```

## Pattern Evolution Strategies

### Handle Company Reporting Changes

```bash
# Company changes role naming - add new pattern without removing old
ep add role --ticker AAPL --group balance --pattern 'NewBalanceSheetFormat.*'

# Company splits combined concept
ep add concept --ticker AAPL --group balance --name "Prepaid Only" --pattern '^PrepaidExpenseCurrent$'
ep add concept --ticker AAPL --group balance --name "Other Current" --pattern '^OtherAssetsCurrent$'
```

### Multi-Pattern Temporal Coverage

```bash
# Catch-all for time series consistency
ep add concept --ticker AAPL --group balance --name "Prepaid Total" \
  --pattern '^(PrepaidExpenseAndOtherAssetsCurrent|PrepaidExpenseCurrent)$'

# Specific patterns for granular analysis
ep add concept --ticker AAPL --group balance --name "Prepaid Specific" \
  --pattern '^PrepaidExpenseCurrent$'
```

## Error Handling

### Pattern Linking Validation

```bash
# Wrong pattern type
ep add role --group balance --id 23
# Error: pattern ID 23 is a concept pattern. Use 'ep add concept' instead.

# Pattern doesn't exist
ep add role --group balance --id 999
# Error: pattern ID 999 not found

# Group doesn't exist
ep add concept --group nonexistent --id 15
# Error: group 'nonexistent' not found
```

### Debugging Missing Data

```bash
# Check if group has role patterns
ep select patterns --ticker AAPL --group balance --type roles

# Check if concepts are found
ep select concepts --ticker AAPL --group balance

# Verify both pattern types exist
ep select patterns --ticker AAPL --group balance
```

## Key Benefits

### Pattern Reuse

- Same pattern can serve multiple groups
- Link by ID avoids duplication
- Cross-company pattern sharing

### Flexible Organization

- Semantic meaning independent of XBRL structure
- Company-specific customization maintained
- Comprehensive and specialized views supported

### Evolutionary Adaptation

- Add new patterns without modifying existing ones
- Handle company reporting changes incrementally
- Maintain historical consistency while adapting to new formats
