# edgar-pipes Cheatsheet

Quick reference for the most common edgar-pipes commands and patterns.

## Global Flags

Work with all commands:

```bash
-d, --debug         # Print pipeline data to stderr
--json              # Output as JSONL
--table             # Output as table
--csv               # Output as CSV
--tsv               # Output as TSV (tab-separated values)
--theme THEME       # Table theme (default, minimal, grid, financial, etc.)
```

---

## New Company Setup

Complete workflow for analyzing a new company:

```bash
# 1. Discover filings
ep probe filings -t TICKER

# 2. Explore available roles (financial statement sections)
ep select filings -t TICKER | ep probe roles

# 3. Create a group (container for patterns)
ep new group Balance

# 4. Find role pattern by filtering role names
ep select filings -t TICKER | ep select roles -p '(?i).*balance.*' -c role_name -u

# 5. Create role pattern once you've identified the right regex
ep new role -t TICKER -n balance -p 'StatementConsolidatedBalanceSheets.*'

# 6. Link role pattern to group
ep add role -g Balance -t TICKER -n balance

# 7. Import concepts from matched roles
ep select filings -t TICKER | ep select roles -g Balance | ep probe concepts

# 8. Inspect concept tags to identify patterns
ep select filings -t TICKER | ep select roles -g Balance | ep select concepts -c tag -u

# 9. Create concept patterns with user IDs for easy reference
ep new concept -t TICKER -n "Cash" -p '^CashAndCashEquivalents.*$' -u 1
ep new concept -t TICKER -n "Inventory" -p '^InventoryNet$' -u 2
ep new concept -t TICKER -n "Total assets" -p '^Assets$' -u 3

# 10. Link concepts to group
ep add concept -g Balance -t TICKER -u 1 2 3

# 11. Extract facts into database
ep update -t TICKER -g Balance

# 12. Generate reports
ep report -t TICKER -g Balance --quarterly
```

---

## Discovery & Exploration

### Probe commands (fetch and cache data from SEC)

```bash
# Discover available filings for a company
ep probe filings -t TICKER [--force]

# Explore roles within filings
ep select filings -t TICKER | ep probe roles

# Explore concepts within specific roles
ep select filings -t TICKER | ep select roles -g GROUP | ep probe concepts
```

### Select commands (query local database)

```bash
# Find entities by ticker
ep select entities -t TICKER

# Filter filings by date or form type
ep select filings -t TICKER --date '>2023-01-01' --form 10-K

# Find roles matching a pattern
ep select filings -t TICKER | ep select roles -p '(?i).*balance.*'

# Show unique concept tags
ep select filings -t TICKER | ep select roles -g GROUP | ep select concepts -c tag -u

# Check for missing concepts (empty = full coverage)
ep select filings -t TICKER | ep select roles -g GROUP | ep select concepts -p 'PATTERN' -m

# List all groups
ep select groups

# List patterns for a company
ep select patterns -t TICKER --type concepts
ep select patterns -t TICKER --type roles
```

---

## Creating Groups & Patterns

### Simple group

```bash
# Create empty group
ep new group GroupName

# Create role pattern
ep new role -t TICKER -n role_name -p 'REGEX_PATTERN'

# Create concept pattern with user ID
ep new concept -t TICKER -n "Concept Name" -p 'REGEX_PATTERN' -u 1

# Link to group
ep add role -g GroupName -t TICKER -n role_name
ep add concept -g GroupName -t TICKER -u 1
```

### Derived group (inherit from parent)

```bash
# Create subgroup with filtered concepts
ep new group Balance.Assets --from Balance -t TICKER -u 1 2 3 4 5

# Create subgroup with pattern filter
ep new group Operations.Revenue --from Operations -t TICKER --pattern '(?i).*revenue.*'
```

---

## Updating & reporting

### Update database

```bash
# Update all groups for a ticker
ep update -t TICKER

# Update specific group
ep update -t TICKER -g GROUP

# Force refresh (re-extract all facts)
ep update -t TICKER --force
```

### Generate reports

```bash
# Basic report
ep report -t TICKER -g GROUP

# Quarterly data only (Q1, Q2, Q3, Q4)
ep report -t TICKER -g Balance --quarterly

# Annual data only (FY)
ep report -t TICKER -g Operations --yearly

# Filter by date range
ep report -t TICKER -g GROUP --date '>=2023-01-01' '<=2024-12-31'

# Filter specific columns
ep report -t TICKER -g GROUP --cols Cash Inventory "Total assets"

# Export to CSV
ep report -t TICKER -g GROUP --quarterly --csv > output.csv
```

---

## Analysis & calculations

### Statistics

```bash
# Show most frequent concepts in group
ep stats concepts -t TICKER -g GROUP --limit 20

# Find concepts appearing in all filings
ep stats concepts -t TICKER -g GROUP --limit 29  # if company has 29 filings
```

### Calculations

```bash
# Add calculated columns
ep report -t TICKER -g Balance | ep calc "Working capital = Current assets - Current liabilities"

# Multiple calculations
ep report -t TICKER -g Balance | ep calc \
  "Current ratio = Current assets / Current liabilities" \
  "Debt to equity = Total debt / Total equity"

# Column names work with or without units
ep report -t TICKER -g Operations | ep calc "Gross margin = GrossProfit / Revenue * 100"
# Works even though report shows "GrossProfit (K)" and "Revenue (K)"

# Track margins over quarters
ep report -t TICKER -g Operations --quarterly | \
  ep calc "Gross margin = GrossProfit / Revenue * 100"

# Rolling window calculations (time series analysis)
ep report -t TICKER -q -g Operations.EPS | \
  ep calc "EPS.TTM = rolling_sum(\"EPS.Basic\")" -w 4
# -w 4 = 4-quarter backward-looking window for trailing twelve months

# Multiple rolling calculations
ep report -t TICKER -q -g Operations | \
  ep calc \
    "Revenue.TTM = rolling_sum(\"Revenue\")" \
    "Revenue.MA4 = rolling_avg(\"Revenue\")" \
    -w 4

# Available rolling functions: rolling_sum, rolling_avg, rolling_min, rolling_max
```

---

## Modifying patterns

### Preview changes (default)

```bash
# Modify concept pattern (preview only)
ep modify concept -u 1 -t TICKER --pattern '^NewPattern$'

# Modify role pattern (preview only)
ep modify role -n role_name -t TICKER --pattern 'NewRolePattern'

# Rename group (preview only)
ep modify group GroupName --rename OldName NewName
```

### Execute changes

```bash
# Execute with -y flag
ep modify concept -u 1 -t TICKER --pattern '^NewPattern$' -y
ep modify role -n role_name -t TICKER --new-name new_role_name -y
ep modify group GroupName --rename OldName NewName -y
```

### Remove patterns from group

```bash
# Remove concept patterns (preview only)
ep modify group GroupName --remove-concept -t TICKER -u 8
ep modify group GroupName --remove-concept -t TICKER -n "Concept Name"

# Remove role patterns (preview only)
ep modify group GroupName --remove-role -t TICKER -n role_name

# Execute with -y flag
ep modify group GroupName --remove-concept -t TICKER -u 8 -y
ep modify group GroupName --remove-concept -t TICKER -n "Concept Name" -y
ep modify group GroupName --remove-role -t TICKER -n role_name -y
```

---

## Deleting data

Preview mode (dry-run) by default:

```bash
# Preview deletion
ep select filings -t TICKER --date '<2020-01-01' | ep delete

# Execute deletion with -y flag
ep select filings -t TICKER --date '<2020-01-01' | ep delete -y

# Delete specific patterns
ep select patterns -t TICKER --uid 99 | ep delete -y

# Delete entire group
ep select groups -n OldGroup | ep delete -y
```

---

## Pipeline examples

Combine commands using pipes:

```bash
# Find and probe roles in one pipeline
ep select filings -t TICKER | ep select roles -p '(?i)balance' | ep probe concepts

# Filter and export
ep select filings -t TICKER --date '>2023-01-01' | ep select roles -g Balance | ep delete -y

# Multi-stage analysis
ep select filings -t TICKER | \
  ep select roles -g Balance | \
  ep select concepts -c tag name -u

# Report with calculations
ep report -t TICKER -g Balance --quarterly | \
  ep calc "Working capital = Current assets - Current liabilities" | \
  ep calc "Current ratio = Current assets / Current liabilities"
```

---

## Column selection & sorting

Specify columns with optional sort direction:

```bash
# Basic column selection
ep select filings -t TICKER -c ticker filing_date form_type

# Sort ascending (+) or descending (-)
ep select filings -t TICKER -c filing_date- form_type+

# Show unique values
ep select roles -t TICKER -c role_name -u

# Combine sorting and uniqueness
ep select concepts -t TICKER -c tag+ -u
```

---

## Tips & tricks

### Pattern development

```bash
# Test pattern coverage before creating
ep select filings -t TICKER | ep select roles -p 'PATTERN' -c role_name -u

# Find concepts missing from pattern
ep select filings -t TICKER | ep select roles -g GROUP | ep select concepts -p 'PATTERN' -m
```

### User IDs

- Use sequential numbering (1, 2, 3...) for organization
- Unique per ticker, can reuse across different companies
- Makes bulk operations easier: `ep add concept -g GROUP -t TICKER -u 1 2 3 4 5`

### Workspaces

```bash
# Initialize new workspace
mkdir aapl && cd aapl
ep init
# Prompts for: user-agent, ticker (AAPL), database path
# Fetches company data from SEC automatically
# Creates database and ep.toml - ready to use!

# Start exploring
ep probe filings              # Fetch SEC filings
ep probe concepts             # Explore XBRL concepts

# Edit ep.toml to define roles and concepts
vi ep.toml

# Validate and build
ep build -c                   # Validate configuration
ep build                      # Extract financial data

# Workspace auto-discovery works from subdirectories
cd analysis/
ep report -g Balance          # Still finds ../ep.toml
```

### Advanced: Copy existing workspace

```bash
# Copy ep.toml from another workspace
mkdir new-company && cd new-company
cp ../aapl/ep.toml .

# Modify for new company
vi ep.toml                    # Update ticker, CIK, patterns

# Initialize and build
ep init                       # Shows current workspace status
ep build -c                   # Validate changes
ep build                      # Build database
```

### Debugging

```bash
# See pipeline data flowing between commands
ep -d select filings -t TICKER | ep -d select roles -g Balance
```

---

## Common workflows

### Adding new concepts to existing group

```bash
# 1. Find candidate tags
ep select filings -t TICKER | ep select roles -g GROUP | ep select concepts -c tag -u

# 2. Create patterns
ep new concept -t TICKER -n "New Concept" -p '^NewTag$' -u 99

# 3. Link to group
ep add concept -g GROUP -t TICKER -u 99

# 4. Update facts
ep update -t TICKER -g GROUP
```

### Creating financial statement groups

```bash
# Balance sheet
ep new group Balance
ep new role -t TICKER -n balance -p 'StatementConsolidatedBalanceSheets.*'
ep add role -g Balance -t TICKER -n balance

# Income statement
ep new group Operations
ep new role -t TICKER -n operations -p 'Statement.*Operations$'
ep add role -g Operations -t TICKER -n operations

# Cash flow
ep new group CashFlow
ep new role -t TICKER -n cashflow -p 'Statement.*CashFlows$'
ep add role -g CashFlow -t TICKER -n cashflow
```

### Quarterly analysis

```bash
# Compare quarterly performance
ep report -t TICKER -g Operations.Revenue --quarterly

# Track margins over quarters
ep report -t TICKER -g Operations --quarterly | \
  ep calc "Gross margin = Gross profit / Revenue * 100"
```

---

## Configuration

```bash
# View workspace status
ep init                      # Shows current workspace info if ep.toml exists

# Validate configuration
ep build -c                  # Validate ep.toml without building

# Workspace structure (ep.toml - auto-discovered)
# edgar-pipes walks up directory tree to find this file
workspace/
  ├── ep.toml               # Single configuration file (user prefs + schema)
  └── db/
      └── edgar.db          # SQLite database (path from ep.toml)
```

---

## Getting Help

```bash
# General help
ep -h

# Command-specific help
ep probe -h
ep select -h
ep report -h

# Subcommand help
ep probe filings -h
ep select roles -h
```
