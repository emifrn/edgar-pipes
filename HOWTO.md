# edgar-pipes How-To Guide

Practical guide for extracting financial data from SEC EDGAR filings using the progressive discovery workflow.

---

## Getting started

### Initialize workspace

```bash
# Create workspace directory
mkdir mycompany && cd mycompany

# Initialize configuration (prompts for user-agent, ticker, database path)
ep init

# Build base database (fetches filings, caches role names)
ep build
```

After `ep build`, the database contains all filings and role names. You won't run `ep build` again until you want to rebuild from scratch using `ep.toml`.

---

## Progressive discovery workflow

The workflow is entirely CLI-based: explore → create patterns in database → extract facts. Use `ep export` to generate `ep.toml` from your database patterns for reproducibility.

### 1. Explore available roles

```bash
# View all role names across filings
ep select filings | ep select roles -c role_name -u

# Find roles matching semantic intent (e.g., balance sheet)
ep select filings | ep select roles -p '(?i).*balance.*' -c role_name -u
```

### 2. Create role pattern

Once identified, create the role in the database:

```bash
ep new role -n balance -p '(?i)^(CONDENSED)?CONSOLIDATEDBALANCESHEETS(Unaudited)?$'
```

### 3. Probe concepts for that role

```bash
# Explore concepts within balance sheet roles (using role name, not pattern)
ep select filings | ep select roles -n balance | ep probe concepts

# View unique concept tags
ep select filings | ep select roles -n balance | ep select concepts -c tag -u
```

### 4. Create concept patterns

Create concepts in the database with user-assigned IDs:

```bash
ep new concept -n "Cash" -p '^Cash(AndCashEquivalentsAtCarryingValue|CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents)$' -u 1
ep new concept -n "Current assets" -p '^AssetsCurrent$' -u 8
ep new concept -n "Total assets" -p '^Assets$' -u 14
```

UIDs are sequential numbers for easy reference. They're unique per company.

### 5. Create groups and link patterns

```bash
# Create group
ep new group Balance

# Link role to group
ep add role -g Balance -n balance

# Link concepts to group
ep add concept -g Balance -u 1 8 14
```

### 6. Extract facts

```bash
# Fetch facts from SEC for the group
ep update -g Balance

# Or update all groups
ep update
```

### 7. Generate reports

```bash
# Quarterly report
ep report -g Balance --quarterly

# Annual report
ep report -g Balance.Assets --yearly

# Export to CSV
ep report -g Balance --quarterly --csv > balance.csv
```

### 8. Export patterns to ep.toml

Once discovery is complete, export your database patterns to `ep.toml` for
version control and reproducibility:

```bash
# Export to stdout (review before saving)
ep export

# Export directly to ep.toml
ep export -o ep.toml
```

The export command automatically reconstructs group hierarchies: groups that
are strict subsets of other groups (within the same role) are marked as derived
using the `from` attribute.

### 9. Repeat for other financial statements

Continue the discovery process for income statements, cash flow, etc.:

```bash
# Income statement
ep new role -n operations -p '(?i)^CONSOLIDATEDSTATEMENTSOFINCOME(Unaudited)?$'
ep new concept -n "Revenue" -p '^RevenueFromContractWithCustomerExcludingAssessedTax$' -u 100
ep new concept -n "Net income" -p '^NetIncomeLoss$' -u 110
ep new group Operations
ep add role -g Operations -n operations
ep add concept -g Operations -u 100 110
ep update -g Operations

# Export updated patterns
ep export -o ep.toml
```

---

## Rebuilding from ep.toml

Once `ep.toml` is complete, rebuild the database from scratch:

```bash
# Delete database
rm -rf db/

# Rebuild from ep.toml
ep init    # Creates fresh database
ep build   # Reads ep.toml, creates all patterns, groups
ep update  # Fetches facts for all groups
```

`ep build` reads from `ep.toml` - it's used for initial setup or clean rebuilds, not during exploration.

---

## Discovery commands

### Probe (fetch and cache from SEC)

```bash
# Fetch latest filings
ep probe filings -t TICKER [--force]

# Cache roles for exploration
ep select filings | ep probe roles

# Cache concepts for specific roles
ep select filings | ep select roles -g GROUP | ep probe concepts
```

### Select (query local database)

```bash
# List entities
ep select entities

# List all filings
ep select filings

# Filter by date
ep select filings --date '>2023-01-01'

# Filter by form type
ep select filings --form 10-K

# List groups
ep select groups

# List patterns
ep select patterns --type roles
ep select patterns --type concepts
```

### Pattern testing

```bash
# Test role pattern coverage
ep select filings | ep select roles -p 'PATTERN' -c role_name -u

# Find concepts missing from pattern (empty = full coverage)
ep select filings | ep select roles -g GROUP | ep select concepts -p 'PATTERN' -m
```

---

## Creating patterns

### Roles

```bash
ep new role -n ROLE_NAME -p 'REGEX_PATTERN'
```

### Concepts

```bash
ep new concept -n "Concept Name" -p 'REGEX_PATTERN' -u UID
```

### Groups

```bash
# Simple group
ep new group GroupName

# Derived group (inherits role from parent)
ep new group Balance.Assets --from Balance -u 1 2 3
```

### Linking patterns to groups

```bash
# Link role to group
ep add role -g GroupName -n role_name

# Link concepts to group (multiple UIDs)
ep add concept -g GroupName -u 1 2 3 4 5
```

---

## Analysis commands

### Statistics

```bash
# Show most frequent concepts in group
ep stats concepts -g Balance --limit 20

# Find concepts appearing in all filings
ep stats concepts -g Balance --limit 29  # if company has 29 filings
```

### Calculations

```bash
# Add calculated columns
ep report -g Balance --quarterly | \
  ep calc "Current ratio = Current assets / Current liabilities"

# Multiple calculations
ep report -g Operations --quarterly | \
  ep calc "Gross margin = Gross profit / Revenue * 100" \
          "Operating margin = Operating income / Revenue * 100"

# Rolling window calculations (TTM = trailing twelve months)
ep report -g Operations --quarterly | \
  ep calc "Revenue.TTM = rolling_sum(\"Revenue\")" -w 4
```

Available rolling functions: `rolling_sum`, `rolling_avg`, `rolling_min`, `rolling_max`

---

## Modifying patterns

### Modify existing patterns

```bash
# Preview changes (dry-run by default)
ep modify concept -u 1 --pattern '^NewPattern$'
ep modify role -n balance --pattern 'NewRolePattern'

# Execute with -y flag
ep modify concept -u 1 --pattern '^NewPattern$' -y
ep modify role -n balance --new-name balance_sheet -y
```

### Remove patterns from groups

```bash
# Preview removal
ep modify group Balance --remove-concept -u 8
ep modify group Balance --remove-role -n old_role

# Execute with -y flag
ep modify group Balance --remove-concept -u 8 -y
ep modify group Balance --remove-role -n old_role -y
```

---

## Exporting patterns

Export database patterns to `ep.toml` format for version control and sharing:

```bash
# Export to stdout (preview)
ep export

# Export to file
ep export -o ep.toml

# Export without header comments
ep export --no-header

# Export specific ticker (if multiple in database)
ep export -t AAPL
```

The export command:
- Reads role patterns, concept patterns, and groups from the database
- Reconstructs group hierarchies (derived groups marked with `from`)
- Generates valid TOML output compatible with `ep build`

**Workflow**: Explore interactively with `ep new` and `ep add`, then `ep export`
to capture your work in `ep.toml` for reproducibility.

---

## Deleting data

Deletion requires explicit confirmation (`-y` flag):

```bash
# Preview deletion (dry-run)
ep select filings --date '<2020-01-01' | ep delete

# Execute deletion
ep select filings --date '<2020-01-01' | ep delete -y

# Delete patterns
ep select patterns --uid 99 | ep delete -y

# Delete groups
ep select groups -n OldGroup | ep delete -y
```

---

## Output formats

```bash
# Table (default)
ep report -g Balance --quarterly

# JSON Lines
ep report -g Balance --quarterly --json

# CSV
ep report -g Balance --quarterly --csv > output.csv

# TSV (gnuplot-compatible)
ep report -g Balance --quarterly --tsv

# Custom table theme
ep report -g Balance --quarterly --theme nobox-minimal
```

Available themes: `default`, `financial`, `minimal`, `grid`, `nobox`, `nobox-minimal` (with `-light`/`-dark` variants)

---

## Column selection and sorting

```bash
# Select specific columns
ep select filings -c ticker filing_date form_type

# Sort ascending (+) or descending (-)
ep select filings -c filing_date- form_type+

# Show unique values
ep select roles -c role_name -u

# Combine with filtering
ep select filings | ep select roles -p '(?i)balance' -c role_name -u
```

---

## Pipeline examples

Combine commands with Unix pipes:

```bash
# Multi-stage exploration
ep select filings | \
  ep select roles -p '(?i)balance' | \
  ep probe concepts

# Filter and analyze
ep select filings --date '>2023-01-01' | \
  ep select roles -g Balance | \
  ep select concepts -c tag name -u

# Report with calculations
ep report -g Operations --quarterly | \
  ep calc "Gross margin = Gross profit / Revenue * 100" | \
  ep calc "Operating margin = Operating income / Revenue * 100"
```

---

## Pattern development tips

### Handle taxonomy changes

Use aggregate patterns to bridge taxonomy transitions:

```bash
ep new concept -n "Cash" \
  -p '^Cash(AndCashEquivalentsAtCarryingValue|CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents)$' \
  -u 1
```

### Organize UIDs

Use numeric ranges by statement type:
- 1-99: Balance sheet
- 100-199: Income statement
- 200-299: Cash flow statement
- 300+: Special metrics (DPS, buybacks, etc.)

### Test before creating

```bash
# Test pattern before committing
ep select filings | ep select roles -p 'PATTERN' -c role_name -u

# Verify coverage across all filings
ep select filings | ep select roles -p 'PATTERN' -m
```

---

## Workspace structure

```
mycompany/
  ├── ep.toml          # Configuration: exported from database via `ep export`
  └── db/
      └── edgar.db     # SQLite database: patterns created via CLI
```

**ep.toml is for reproducibility** - use `ep export -o ep.toml` to capture your
database patterns. When complete, use `ep build` to recreate the database from
scratch on another machine or after resetting.

Workspace is auto-discovered by walking up the directory tree from current location.

---

## Getting help

```bash
# General help
ep -h

# Command-specific help
ep probe -h
ep select -h
ep new -h
ep add -h
ep update -h
ep export -h

# Subcommand help
ep probe filings -h
ep select roles -h
ep new concept -h
ep add role -h
```

---

## Example: Complete balance sheet workflow

```bash
# 1. Initialize workspace (done once)
mkdir mycompany && cd mycompany
ep init
ep build

# 2. Explore and identify balance sheet role
ep select filings | ep select roles -p '(?i)balance' -c role_name -u

# 3. Create role pattern
ep new role -n balance -p '(?i)^CONSOLIDATEDBALANCESHEETS(Unaudited)?$'

# 4. Probe concepts for that role
ep select filings | ep select roles -n balance | ep probe concepts
ep select filings | ep select roles -n balance | ep select concepts -c tag -u

# 5. Create concept patterns
ep new concept -n "Cash" -p '^CashAndCashEquivalents.*$' -u 1
ep new concept -n "Inventory" -p '^InventoryNet$' -u 7
ep new concept -n "Current assets" -p '^AssetsCurrent$' -u 8
ep new concept -n "Total assets" -p '^Assets$' -u 14
ep new concept -n "Current liabilities" -p '^LiabilitiesCurrent$' -u 21
ep new concept -n "Total liabilities" -p '^Liabilities$' -u 24
ep new concept -n "Total equity" -p '^StockholdersEquity$' -u 28

# 6. Create groups
ep new group Balance
ep new group Balance.Assets --from Balance -u 1 7 8 14
ep new group Balance.Summary --from Balance -u 8 14 21 24 28

# 7. Link patterns to main group
ep add role -g Balance -n balance
ep add concept -g Balance -u 1 7 8 14 21 24 28

# 8. Extract facts
ep update -g Balance

# 9. Generate reports
ep report -g Balance.Summary --quarterly

# 10. Export patterns to ep.toml for version control
ep export -o ep.toml
```

Later, rebuild from scratch:

```bash
rm -rf db/
ep init
ep build    # Reads ep.toml, recreates everything
ep update   # Fetches facts
```
