## Journaling system

The system maintains a persistent log of complete pipeline commands in local
journal files. When pipelines terminate at the terminal (table output), main.py
writes the full command sequence with timestamps and success/error status. This
enables replay functionality for database reconstruction and provides an audit
trail of exploration activities. The journal system bridges the gap between
exploratory data analysis and reproducible research workflows.

### Current Format

The journal uses an indexed, fixed-width format with visual separation:

```
  1  2025-09-14  13:29:23  ✓  │  probe filings --ticker AEO --force
  2  2025-09-14  13:30:31  ✓  │  select filings --ticker AEO | probe roles
  3  2025-09-14  13:30:46  ✓  │  select filings --ticker AEO | select roles --pattern 'StatementConsolidatedBalanceSheets1?$|BALANCESHEETS$' | probe concepts
  4  2025-09-20  14:26:47  ✓  │  new balance --ticker AEO
  5  2025-09-20  14:43:01  ✓  │  add roles --ticker AEO --group balance --pattern 'StatementConsolidatedBalanceSheets1?$|BALANCESHEETS$'
  6  2025-09-21  14:38:54  ✓  │  add concept --ticker AEO --group balance --name 'Cash' --pattern '^CashAndCashEquivalentsAtCarryngValue$'
  7  2025-09-23  04:18:27  ✓  │  add concept --ticker AEO --group balance --name 'Short term investments' --pattern '^ShortTermInvestments$'
  8  2025-09-23  04:24:37  ✓  │  add concept --ticker AEO --group balance --name 'Inventory' --pattern '^InventoryNet$'
  9  2025-09-23  04:30:57  ✓  │  add concept --ticker AEO --group balance --name 'Accounts receivable' --pattern '^AccountsReceivableNetCurrent$'
 10  2025-09-23  04:56:43  ✓  │  add concept --ticker AEO --group balance --name 'Prepaid expense and other assets current' --pattern '^(PrepaidExpenseAndOtherAssetsCurrent|PrepaidExpenseCurrent)$'
 11  2025-09-23  05:12:35  ✓  │  add concept --ticker aeo --group balance --name 'Prepaid expense current' --pattern '^PrepaidExpenseCurrent$'
 12  2025-09-23  05:13:02  ✓  │  add concept --ticker aeo --group balance --name 'Other assets current' --pattern '^OtherAssetsCurrent$'
 13  2025-09-23  05:25:53  ✓  │  add concept --ticker aeo --group balance --name 'Current assets' --pattern '^AssetsCurrent$'
 14  2025-09-23  05:26:04  ✓  │  select patterns --ticker aeo --group balance --type concepts
```

### Format Features

- **Sequential indexing**: 3-digit right-aligned indices for easy reference
- **Separated date/time**: Improved readability over ISO timestamp format
- **Visual separator**: `│` (box drawing character) distinguishes metadata from commands
- **Fixed-width fields**: Consistent alignment for visual scanning
- **Status symbols**: `✓` for success, `✗` for errors

### Journal Management

**Multiple journals**: Support for named journals for different projects

```bash
ep journal use aeo           # Switch to project journal
ep journal use               # Switch to default journal (shorthand)
ep journal list              # List all journals with configuration
ep journal current           # Show active journal
```

**Auto-creation**: Journals are automatically created when first accessed,
eliminating setup friction.

**Configuration transparency**: The `list` command shows the journal directory
location and environment variable configuration:

```
Journal directory: /home/user/.config/edgar-pipes
  (default location, override with EDGAR_PIPES_JOURNAL_HOME)

Available journals:
  aeo            (current)   journal-aeo.txt
  default                    journal.txt
```

### Replay Functionality

**Simple cases**: Execute entire journals

```bash
ep journal replay             # Replay entire current journal
ep journal replay aeo         # Replay entire aeo journal
```

**Index-based replay**: Execute specific commands by index

```bash
ep journal replay 5           # Replay command #5
ep journal replay 5:8         # Replay commands 5-8  
ep journal replay 5:8,10      # Replay commands 5-8 and 10
```

**Cross-journal replay**: Execute commands from any journal using bracket syntax

```bash
ep journal replay default[1:5,8,9]                       # From default journal
ep journal replay AEO[2,4:5,3,7,1:3]                     # Complex ordering with duplicates
ep journal replay default[1:5] aeo[3:7] main[10:12]      # Multiple journals in sequence
```

**Execution order preservation**: Commands execute in the exact order
specified, including duplicates, enabling sophisticated workflow composition.

### Real-World Discovery Patterns

The AEO journal demonstrates typical concept discovery workflows:

**Phase 1: Basic concept mapping** (entries 6-9)

- Start with fundamental balance sheet items (Cash, Short term investments, Inventory, Accounts receivable)
- Use precise patterns for initial concept capture

**Phase 2: Handle reporting variations** (entries 10-12)  

- Discover temporal changes in reporting (PrepaidExpenseAndOtherAssetsCurrent vs PrepaidExpenseCurrent)
- Create catch-all patterns for consistent time series coverage
- Add specific patterns for disaggregated analysis

**Phase 3: Systematic completion** (entries 13-14)

- Add comprehensive concepts (Current assets)
- Verify pattern coverage with inspection commands

This pattern shows how users iteratively build complete financial concept maps
by starting with core items and progressively handling reporting complexities.

### Workflow Patterns

**Experimentation to production**: Use default journal for exploration, then
replay successful sequences into project journals:

```bash
# Experiment in default journal - try different approaches
ep select concepts --ticker AEO --pattern ".*Prepaid.*"

# Switch to project journal and replay successful commands  
ep journal use aeo
ep journal replay default[1:5,8,9]
```

**Incremental development**: Build on previous work by replaying foundations
and adding new concepts:

```bash
# Replay basic setup, then experiment with new concepts
ep journal replay aeo[1:5] 
# ... experiment with new patterns ...
# ... add successful new patterns to journal ...
```

### Error Handling

**Validation strategy**: All journal specifications are validated before any
execution begins:

- Journal existence verification
- Index range validation 
- Command status verification (only successful commands can be replayed)
- Syntax validation for bracket specifications

**Abort on error**: If any validation fails, the entire replay operation aborts
with a clear error message, ensuring predictable behavior and preventing
partial execution states.

### Advanced Usage

**Workflow development**: The journal enables iterative refinement of financial
data discovery processes. Users can experiment with patterns, validate
coverage, and build comprehensive concept maps through documented, repeatable
sequences.

**Knowledge transfer**: Cross-journal replay enables transferring discovery
patterns between companies while adapting for company-specific variations.

### Implementation Notes

**Storage**: Journals stored in `~/.config/edgar-pipes/` (configurable via `EDGAR_PIPES_JOURNAL_HOME`)
**Naming convention**: Default journal uses `journal.txt`, named journals use `journal-{name}.txt`
**Pipeline integration**: Commands are journaled when pipelines terminate at the terminal (table output)
**Metadata filtering**: Journal management commands (use, list, current) are not journaled to avoid noise
**Index management**: Sequential numbering with automatic gap handling and collision avoidance
