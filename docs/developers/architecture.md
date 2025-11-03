# Edgar-pipes architecture

High-level overview of the system design and architectural choices. This
document provides the conceptual framework for understanding how edgar-pipes
components work together.

For detailed implementation information, see:
- **[Module Documentation](modules/)** - In-depth coverage of each component
- **[Design Decisions](decisions/)** - Rationale behind key architectural choices
- **[Examples](../examples/)** - Sample workflows demonstrating the system in action

## Component layers

The edgar-pipes command fetches company financial data from the public database
Edgar and stores a subset in a local SQLite3 database for persistence and fast
access. The command uses the opensource Arelle library for inspection of XBRL
datasets. The command includes the following components:

1. CLI component (`edgar/cli/`) - 15 subcommands (probe, select, new, add,
   update, report, etc.). Each command follows the Cmd protocol: receives `Cmd`
   from stdin, returns `Result[Cmd, str]`. Commands compose via Linux pipes for
   complex data manipulations. See [cli.md](modules/cli.md) for details.

2. Database component (`edgar/db/`) - SQLite-based storage with two modules:

   - `store.py`: Schema definition and CRUD operations (insert, select, delete)
   - `queries/`: Business logic modules (entities, filings, roles, concepts, facts)

   See [db.md](modules/db.md) for schema and query details.

3. XBRL component (`edgar/xbrl/`) - Arelle wrapper for parsing XBRL files:

   - `arelle.py`: Extract roles, concepts, facts from XBRL instance documents
   - `sec_api.py`: Fetch filing metadata from SEC EDGAR API
   - `facts.py`: Fact extraction and context processing

   See [xbrl.md](modules/xbrl.md) for API and parsing details.

4. Cache component (`edgar/cache.py`) - Smart resolver implementing
   fetch-on-demand: checks local DB → fetches from SEC API → caches → returns.
   Provides transparent network/database abstraction to CLI commands. See
   [cache.md](modules/cache.md) for resolution logic.

5. Journal component (`edgar/cli/journal.py`) - Automatic command tracking
   with replay capability. Journals stored in JSONL format enable reproducible
   workflows, templates, and shareable company libraries. See
   [cli.md](modules/cli.md#journal-management) for journal system details.

6. Pipeline orchestration (`edgar/pipeline.py`) - Packet envelope management
   for command composition. Tracks pipeline history for journaling and debugging.
   See [main_and_pipeline.md](modules/main_and_pipeline.md) for protocol details.

7. Configuration (`edgar/config.py`) - User agent, database paths, themes.
   Precedence: env vars → config file → defaults. See
   [config.md](modules/config.md) for configuration management.

## Command execution flow

Every `ep` command follows this lifecycle (edgar/main.py):

1. Parse arguments, load configuration from ~/.config/edgar-pipes/config.toml
2. Read packet from stdin via `pipeline.read()` (None if start of pipeline)
3. Build pipeline history by appending current command
4. Execute command function: `args.func(cmd, args)` returns `Result[Cmd, str]`
5. Handle result:
   - Error: Print to stderr, journal with ERROR status
   - Success: Determine output format (table/JSON/CSV/packet)
   - If piped: Write JSON packet with pipeline history
   - If terminal: Format as table/JSON/CSV based on flags

Packet format preserves pipeline context for debugging and journaling:

```json
{
  "ok": true,
  "name": "select_filings",
  "data": [{"cik": "0000320193", "ticker": "aapl", ...}],
  "pipeline": ["select filings -t AAPL", "probe roles"]
}
```

## Architectural ideas

### Patterns for managing variability

The pattern system solves the core variability problem: filings use different
names for the same financial concepts, both across companies and over time
within a single company. Role URIs and concept tags may change between filings
as companies refine their reporting structure or update taxonomy versions.
Rather than hardcoding every possible variation, users define regex patterns
that capture semantic intent. This enables both cross-sectional analysis across
companies and longitudinal analysis for the same company over time.

Groups bundle role patterns (where to look) and concept patterns (what to
extract), enabling reusable, company-specific extraction rules. Pattern tables
are company-specific (linked by CIK), allowing different companies to have
different extraction rules while sharing group names like "Balance" or
"Operations". The many-to-many relationship means patterns are reusable: the
same role pattern can serve multiple groups (Balance, Balance.Assets,
Balance.Liabilities), while each group maintains its own concept selection.

### Pipeline protocol

Financial analysis is exploratory. Rather than forcing users into rigid
workflows, the pipeline enables composition:

```bash
ep select filings --ticker AAPL |
   ep select roles --group balance |
   ep probe concepts --pattern ".*Assets.*"
```

Each command filters/transforms data, enabling progressive refinement. Format
detection (edgar/pipeline.py) switches between human-readable tables
(terminal) and JSON packets (pipes) automatically.

### Cache as smart resolver

The cache layer (edgar/cache.py) implements resolve-on-demand:

- `resolve_entities()`: Check DB → Fetch from SEC API → Cache → Return
- `resolve_filings()`: Respects `--force` flag and date filters
- `resolve_roles()`: Lazy-load XBRL structure only when needed
- `resolve_concepts()`: Links concepts to roles automatically

This eliminates manual cache management and provides transparent network/database
abstraction to CLI commands. XBRL files (10-50MB) are expensive to parse, so
metadata (roles, concepts) is cached aggressively.

### SQLite for fast retrieval

- Single-file database (portable, simple deployment)
- Acts as both cache (filing metadata) and warehouse (extracted facts)

The schema maps XBRL hierarchy to relational model while adding the pattern
layer for semantic extraction (edgar/db/store.py).

### Result types

All fallible operations return `Result[T, str]` (edgar/result.py):

```python
result = cache.resolve_entities(conn, tickers)
if is_ok(result):
    entities = result[1]  # Safe unwrap
else:
    return result  # Propagate error up
```

Forces explicit error handling at every layer, eliminates exception-based
control flow and silent failures. Trade-off: More verbose, but errors are
tracked explicitly through the call chain.

## Data model

### Core hierarchy (XBRL → Database)

```
Entity (Company)
  ↓
Filing (10-K, 10-Q)              → filings, dei
  ↓
Role (Balance Sheet, etc.)       → roles (URI tail stored)
  ↓
Concept (Assets, Revenue)        → concepts (taxonomy + tag + name)
  ↓
Fact (value + context)           → facts, contexts, units, dimensions
```

Key mappings:

- Role URIs are normalized: `http://apple.com/role/BalanceSheets` → `BalanceSheets`
- Concepts include taxonomy namespace: `us-gaap:CashAndCashEquivalents`
- Contexts track temporal periods: instant, quarter, semester, year
- Facts link role + concept + context + unit (UNIQUE constraint)

### Pattern system (edgar-pipes layer)

```
Group (semantic container: "Balance", "Operations")
  ↓ many-to-many
Role Patterns (regex: where to look in filings)
Concept Patterns (regex: what to extract, company-specific)
  ↓ pattern matching
Matches against actual Roles and Concepts in filings
```

Pattern tables (edgar/db/store.py):

- `role_patterns`: company-specific (CIK), links via `group_role_patterns`
- `concept_patterns`: includes optional `uid` for bulk operations
- Many-to-many enables:
  - Same group name across companies with different patterns
  - Pattern reuse (one role pattern serves multiple groups)
  - Hierarchical derivation: `Balance.Assets --from Balance`

## XBRL integration

edgar-pipes wraps the Arelle library (edgar/xbrl/arelle.py) for XBRL parsing:

Core functions:

- `load_model(url)`: Downloads and parses XBRL instance documents
- `roles(model)`: Extracts presentation role URI tails from linkbase
- `role_facts(model, role)`: Traverses presentation hierarchy to find facts
- `role_concepts(model, role)`: Deduplicates concepts from role facts
- `extract_dei(model)`: Pulls Document Entity Information (fiscal periods, etc.)

Challenges handled:

- Large files: XBRL instances can be 10-50MB. Cache layer (edgar/cache.py:142-180)
  stores extracted metadata to avoid re-parsing
- URI normalization: Store role tail instead of full URI for readability
- Malformed DEI dates: `extract_dei()` validates and normalizes fiscal period dates
- Presentation traversal: Must walk parent-child arcroles to build fact hierarchy

The cache layer prevents redundant XBRL downloads by storing roles and concepts
after first parse.
