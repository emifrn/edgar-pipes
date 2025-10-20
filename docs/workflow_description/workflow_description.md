## Workflow description

Edgar's core strength lies in supporting iterative financial data exploration through command composition. Users typically follow a pattern: 

(1) probe filings to cache metadata
(2) explore roles through pattern matching
(3) selectively probe concepts for interesting roles
(4) define logical groupings and patterns
(5) compose specialized groups
(6) extract facts

Below a more detailed description of a typical interactive discovery workflow.

### Phase 1: Entity and filing discovery

#### Entity resolution

Fetches company metadata from SEC API and caches recent filings. This populates the entities and filings tables with lightweight metadata.

```
% ep probe filings --ticker AEO

[1/1] Fetching filings for AEO... cached 29 filings
name                           ticker           cik  access_no             filing_date    form_type
-----------------------------  --------  ----------  --------------------  -------------  -----------
AMERICAN EAGLE OUTFITTERS INC  aeo       0000919012  0000950170-25-113811  2025-09-09     10-Q
AMERICAN EAGLE OUTFITTERS INC  aeo       0000919012  0000950170-25-082416  2025-06-05     10-Q
AMERICAN EAGLE OUTFITTERS INC  aeo       0000919012  0000950170-25-042746  2025-03-20     10-K
...
```

**Force fresh data**: Use `--force` to bypass cache and fetch latest filings when new documents may have been published:

```
% ep probe filings --ticker AEO --force
[Bypasses cache and fetches directly from SEC API]
```

#### Data verification

Verify cached entities and filings:

```
% ep select entities --ticker AEO
% ep select filings --ticker AEO
```

### Phase 2: Role discovery and pattern definition

#### Role discovery

Downloads XBRL models and extracts role names. Moderately expensive as it parses XBRL structure.

```
% ep select filings --ticker AEO | probe roles

Processing 29 filing(s) for role discovery...
[ 1/29] 0000950170-25-113811... cached 15 roles
[ 2/29] 0000950170-25-082416... cached 15 roles
...
```

#### Role pattern exploration

Tests role patterns against cached role names with AND logic - both group patterns and explicit patterns must match:

```
% ep select roles --ticker AEO --pattern 'Balance.*'
% ep select roles --ticker AEO --group balance --pattern '^Statement'
[Returns roles matching BOTH group patterns AND explicit pattern]
```

#### Create logical group and define patterns

```
% ep new balance --ticker AEO
% ep add roles --ticker AEO --group balance --pattern 'StatementConsolidatedBalanceSheets.*|.*BALANCESHEETS.*'
```

### Phase 3: Concept discovery and pattern mapping

#### Selective concept discovery

Downloads XBRL models, parses presentation linkbases, extracts concepts from matched roles:

```
% ep select filings --ticker AEO | select roles --group balance | probe concepts

Processing 28 filing-role combination(s)...
[ 1/28] 0000950170-25-113811 / StatementConsolidatedBalanceSheets1... cached 156 concepts
...
```

#### Concept pattern identification

Explore concepts using pattern matching with AND logic:

```
% ep select concepts --ticker AEO --group balance --pattern ".*Current.*"
[Applies group patterns AND additional pattern filter]
```

#### Comprehensive concept mapping strategies

Build comprehensive concept foundations that serve multiple analytical purposes:

**Foundation group approach**:

```bash
# Build comprehensive balance sheet concept map
ep add concept --ticker AEO --group balance --name "Cash" --pattern '^CashAndCashEquivalentsAtCarryngValue$'
ep add concept --ticker AEO --group balance --name "Short term investments" --pattern '^ShortTermInvestments$'
ep add concept --ticker AEO --group balance --name "Inventory" --pattern '^InventoryNet$'
ep add concept --ticker AEO --group balance --name "Accounts receivable" --pattern '^AccountsReceivableNetCurrent$'
ep add concept --ticker AEO --group balance --name "Prepaid expense and other assets current" --pattern '^(PrepaidExpenseAndOtherAssetsCurrent|PrepaidExpenseCurrent)$'
ep add concept --ticker AEO --group balance --name "Current assets" --pattern '^AssetsCurrent$'
```

**Multi-pattern approach for temporal variations**:
Handle cases where companies change aggregation levels over time:

```bash
# Catch-all pattern for consistent time series
ep add concept --ticker AEO --group balance --name "prepaid_total" --pattern '^(PrepaidExpenseCurrent|PrepaidExpenseAndOtherAssetsCurrent)$'

# Specific disaggregated components for detailed analysis
ep add concept --ticker AEO --group balance --name "prepaid_only" --pattern '^PrepaidExpenseCurrent$'
ep add concept --ticker AEO --group balance --name "other_current_assets" --pattern '^OtherAssetsCurrent$'
```

This strategy ensures:

- Complete time series coverage through catch-all patterns
- Granular analysis capabilities when disaggregated data is available
- Adaptability to changing reporting formats

### Phase 4: Group composition

#### Derive specialized analytical views

The many-to-many architecture enables composing specialized from comprehensive groups without duplicating concept patterns:

**Create focused analytical groups**:

```bash
# Derive current assets from comprehensive balance sheet
ep new 'Current assets' --from balance --names 'Cash|Short|Inventory|Accounts|Prepaid|Other'

# Create liquidity-focused view
ep new 'Liquid assets' --from balance --names 'Cash|Short' --exclude 'Restricted'

# Build working capital components
ep new 'Working capital assets' --from balance --names 'Cash|Inventory|Accounts|Prepaid'
```

**Multi-source derivation**:

```bash
# Combine patterns from multiple source groups
ep new 'Key ratios' --from 'balance' 'income' 'cash' --names 'Cash|Revenue|Debt'
```

#### Group hierarchy management

Verify and inspect group relationships:

```bash
# View all groups for a company
ep select groups --ticker AEO

# Inspect group composition
ep select patterns --ticker AEO --group balance
ep select patterns --ticker AEO --group 'Current assets'

# Compare group overlaps
ep select patterns --ticker AEO --group 'Liquid assets'
```

#### Group strategy patterns

**Bottom-up approach**: Build comprehensive foundations first

1. Create broad categorical groups (balance, income, cash)
2. Populate with complete concept coverage
3. Derive specialized analytical views
4. Refine for specific analysis needs

**Analytical specialization**: Layer groups for different purposes

- **Comprehensive groups**: Full statement coverage (balance, income)
- **Analytical groups**: Focused financial analysis (current assets, profitability)
- **Research groups**: Specific investigation themes (liquidity, leverage)

### Phase 5: Pipeline debugging and inspection

#### Debug pipeline transformations

Use the global `-d/--debug` flag to inspect data at any pipeline stage:

```
% ep select filings --ticker AEO | ep -d select roles --group balance | select concepts --pattern Cash

=== DEBUG: roles (29 records) ===
[Shows complete role data with counts and table format]
==================================================
[Final output continues normally]
```

The debug output goes to stderr and doesn't interfere with pipeline data flow.

### Phase 6: Dynamic querying and fact extraction

#### Query concept matches

Fast regex matching against cached concepts with multiple access modes:

**Pipeline data (explicit filing-role pairs)**:

```bash
ep select filings | select roles --group balance | select concepts --pattern ".*Assets.*"
```

**Group-based queries (applies to all cached filings)**:

```bash
# Query comprehensive groups
ep select concepts --ticker AEO --group balance --name "cash"

# Query derived groups
ep select concepts --ticker AEO --group 'Current assets' --pattern ".*Cash.*"

# Cross-group analysis
ep select concepts --ticker AEO --group 'Liquid assets'
```

**Pattern refinement**: Use additional patterns to narrow results:

```bash
ep select concepts --ticker AEO --group balance --pattern ".*Current.*"
```

#### Extract financial facts

Downloads XBRL instances and extracts numerical facts:

```
% ep update --ticker AEO --group balance --name "cash"

== aeo (CIK 0000919012) ==
  - 0000950170-25-113811  2025-09-09
    • inserted: 12 fact(s)
```

#### Scaling update operations

```bash
# Concept-level (development/testing)
ep update --ticker AEO --group 'Current assets' --name "cash"

# Group-level (typical usage)  
ep update --ticker AEO --group 'Current assets'

# Comprehensive analysis
ep update --ticker AEO --group balance

# Entity-level (batch processing)
ep update --ticker AEO

# System-wide (production)
ep update
```

### Discovery workflow patterns

#### Group-first strategy

Modern Edgar workflows emphasize building comprehensive concept foundations that serve multiple analytical purposes:

1. **Comprehensive mapping**: Build complete statement-level groups (balance, income, cash)
2. **Pattern completeness**: Handle temporal variations and aggregation changes
3. **Analytical derivation**: Create specialized views from comprehensive foundations
4. **Refinement**: Iteratively improve both foundations and derived groups

#### Compositional analysis workflows

**Financial statement analysis**:

```bash
# Phase 1: Build comprehensive foundations
ep new balance --ticker AEO
ep add concept --ticker AEO --group balance --name "Cash" --pattern "^Cash.*$"
# ... build complete balance sheet concept map

# Phase 2: Derive analytical views
ep new 'Current assets' --from balance --names 'Cash|Short|Inventory|Accounts|Prepaid|Other'
ep new 'Liquid assets' --from 'Current assets' --names 'Cash|Short'

# Phase 3: Cross-group analysis
ep select concepts --ticker AEO --group 'Liquid assets'
ep update --ticker AEO --group 'Liquid assets'
```

**Cross-company pattern transfer**:

```bash
# Develop patterns for one company
ep journal use aeo
# ... build comprehensive concept maps

# Transfer successful patterns to other companies
ep journal use retail_analysis
ep journal replay aeo[5:15]  # Replay successful concept mapping sequences
# ... adapt patterns for different companies
```

#### Using missing functionality for discovery

The `--missing` flag transforms exploration from guesswork into targeted discovery:

**Role discovery**: Find filings with unexpected role names
**Concept discovery**: Identify filing-role pairs where expected concepts are absent
**Group coverage**: Validate completeness of derived groups

```bash
# Find gaps in group coverage
ep select concepts --ticker AEO --group 'Current assets' --missing
# Identify filing-role pairs where current asset concepts are unexpectedly absent
```

#### Advanced group management

**Pattern reuse validation**:

```bash
# Verify pattern efficiency - same patterns serving multiple groups
ep select patterns --ticker AEO --group balance | group --by pattern
# Shows which patterns are reused across multiple groups
```

**Hierarchical verification**:

```bash
# Ensure derived groups are proper subsets of source groups
ep select patterns --ticker AEO --group balance --cols pattern | \
  summary --agg count  # Total balance sheet patterns

ep select patterns --ticker AEO --group 'Current assets' --cols pattern | \
  summary --agg count  # Should be subset of balance patterns
```

#### Journal-driven workflow development

Use journals to capture and replay successful discovery sequences, including group composition:

```bash
# Develop comprehensive workflow in default journal
# Build foundations, derive groups, validate coverage

# Transfer to project journal
ep journal use aeo
ep journal replay default[1:15,20:25]  # Include group derivation commands

# Cross-project knowledge transfer
ep journal use retail_comp
ep journal replay aeo[5:10] msft[8:12]  # Combine successful patterns
```

**Real-world AEO journal example**:

```
14  2025-09-23  05:26:04  ✓  │  select patterns --ticker aeo --group balance --type concepts
15  2025-09-24  10:15:22  ✓  │  new 'Current assets' --from balance --ticker aeo --names 'Cash|Short|Inventory|Accounts|Prepaid|Other'
16  2025-09-24  10:16:45  ✓  │  select groups --ticker aeo
17  2025-09-24  10:17:12  ✓  │  select patterns --ticker aeo --group 'Current assets'
```

This demonstrates the evolution from individual concept mapping (entries 1-14) to compositional group creation (entry 15) and validation (entries 16-17).

### Advanced compositional strategies

#### Multi-dimensional analysis

Create overlapping analytical views for different research questions:

```bash
# Liquidity analysis
ep new 'Liquid assets' --from balance --names 'Cash|Short'
ep new 'Working capital' --from balance --names 'Cash|Inventory|Accounts|Prepaid'

# Profitability analysis  
ep new 'Core revenue' --from income --names 'Revenue|Sales' --exclude 'Discontinued'
ep new 'Operating costs' --from income --names 'Cost|Expense' --exclude 'Interest|Tax'

# Risk analysis
ep new 'Debt instruments' --from balance --names 'Debt|Loan|Bond|Note'
ep new 'Off balance sheet' --from balance --names 'Lease|Commitment|Contingent'
```

#### Pattern evolution management

Handle evolving financial reporting through layered group strategies:

```bash
# Temporal stability groups - consistent across reporting periods
ep new 'Core assets' --from balance --names 'Cash|Inventory|Equipment'

# Adaptive groups - handle reporting changes
ep new 'Flexible current' --from balance --names 'Prepaid' --exclude 'Combined'
# Pattern handles both PrepaidExpenseCurrent and PrepaidExpenseAndOtherAssetsCurrent
```

This compositional approach transforms Edgar from a pattern matching tool into a financial taxonomy management system, enabling sophisticated, reusable analytical frameworks.
