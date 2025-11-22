# edgar-pipes

**Extract and analyze financial data from SEC EDGAR filings using a progressive discovery process.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

## What is edgar-pipes?

edgar-pipes (ep) is a CLI tool for extracting financial data from SEC EDGAR
filings. The command fetches companies' filing information and stores it in a
local SQLite3 database for persistence and fast retrieval. It uses the EDGAR
API and leverages Arelle, an open-source XBRL library, for the extraction of
selected financial data.

The ep command is designed to operate with Linux pipes ('|'), where the output
of a subcommand becomes the input of the next one. This mechanism enables
composable and highly adaptable data-pipelines with zero programming
requirements. This approach shifts the focus from building software for
financial data extraction to a more interactive exploration of financial
information directly in the Linux terminal, and so enabling all kinds of
analysis and reporting solutions.

The typical edgar-pipes workflow includes subcommands that **probe** XBRL
filings via EDGAR API. **Select** tags with their historical variations via
pattern matching across filings. Create **new** user defined groups for
consistent data retrieval over time and across companies. **Update** a local
SQLite3 database with the latest XBRL facts, and **report** financial data
based on previously defined groups, e.g. 'Balance', 'Balance.Assets',
'Balance.Assets.Current', 'Operations', 'CashFlow', etc. etc. 

### Reproducible workflows

The ep command includes an explicit journaling system for recording command
sessions. Use the `-j` flag to record commands to journals. The journaling
system supports named journals and can replay workflows fully or partially via
indexing syntax. Journals can be used as templates for new company analysis, as
a compact backup system (storing commands instead of data), or they can be used
as part of shareable company libraries

In short, edgar-pipes enables a progressive discovery workflow that allows
users to:

1. **Discover** what data exists in filings interactively
2. **Select** filings, roles and concepts they care about
3. **Extract** financial facts into a local database with incremental updates
4. **Report** tabular data from local database in the preferred format
5. **Update** with latest facts as they become available with new Company filings


## Key Concepts

edgar-pipes uses a three-layer architecture for organizing financial data:

### Roles

Define **where** to look in XBRL filings (which sections to examine). In XBRL
documents, presentation roles (also called role URIs or networks) organize
financial data into sections like balance sheets, income statements, cash flow
statements and many more. Each role has a URI identifier such as
`http://company.com/role/ConsolidatedBalanceSheets`. However, role URIs often
change between filings, even for the same company, as reporting structures are
refined. 

A role in edgar-pipes consists of:

- **name**: A user defined semantic label (e.g., "Balance Sheet")
- **pattern**: A regex that matches role URIs (e.g., `".*BalanceSheet.*"`)

Pattern matching ensures data extraction remains consistent across time,
enabling reliable historical tracking without manual intervention.

Role patterns are:

- Shared across multiple groups (Balance, Balance.Assets, Balance.Liabilities)
- Company-specific

### Concepts

Define **what** to extract (which financial metrics). In XBRL, concepts are
the fundamental data elements that represent financial line items like
"CashAndCashEquivalentsAtCarryingValue",
"RevenueFromContractWithCustomerExcludingAssessedTax", or
"AccountsPayableCurrent". Each concept has a tag name from a taxonomy
(typically US-GAAP) that identifies what the number represents.

However, concept tags frequently change between companies reporting similar
items. For example, "Cash" might appear as `CashAndCashEquivalents`,
`CashAndCashEquivalentsAtCarryingValue`, or
`CashCashEquivalentsAndShortTermInvestments` depending on the taxonomy version
and company choice.

A concept pattern in edgar-pipes consists of:

- **name**: A user-defined semantic label (e.g., "Cash", "Revenue")
- **pattern**: A regex matching concept tags (e.g., `"^CashAndCashEquivalents.*$"`)
- **uid**: A user-assigned numeric ID for easy reference

Pattern matching abstracts away taxonomy variations, mapping multiple similar
tags to a single consistent label across time and companies.

Concept patterns are:

- Company-specific (different companies may need different patterns)
- Linked to one or more groups
- Tracked by uid for convenient bulk operations

### Groups

Groups are an edgar-pipes concept (not part of XBRL) that organize patterns
into cohesive analytical views for reporting.

A group brings together:

- **Role patterns**: Define the data scope (which filing sections to examine)
- **Concept patterns**: Define what to extract (which financial metrics)
- **Hierarchy**: Groups can be derived from parent groups with filtered concepts

Example hierarchy: `Balance` -> `Balance.Assets` -> `Balance.Assets.Current`

Multiple groups can share the same role patterns (data scope) while maintaining
different concept selections. Groups are the unit of extraction and
reporting. When you run `ep update -t AAPL -g Balance`, edgar-pipes extracts
facts matching that group's role and concept patterns for the given ticker.


## Quick Start

**New to edgar-pipes?** Check out [CHEATSHEET.md](CHEATSHEET.md) for a quick
command reference with common workflows and patterns.

**Working with AI agents?** The `ep` command's composable pipeline architecture
mechanisms make it well-suited for AI-driven financial analysis. AI agents can
systematically discover, validate, and extract financial data using the
progressive discovery workflow. See
[docs/agents/AI_AGENT_GUIDE.md](docs/agents/AI_AGENT_GUIDE.md) for
AI Agent guidance, validation strategies, and best practices for accurate
financial data extraction.

### Installation

```bash
# Clone repository
git clone https://github.com/emifrn/edgar-pipes.git
cd edgar-pipes

# Install package
pip install -e .
```

See [INSTALL.md](INSTALL.md) for detailed installation instructions.

### First Run Setup

The first time you run any `ep` command, you'll be prompted to configure your
identity for SEC EDGAR API requests:

```bash
$ ep probe filings -t AAPL

Welcome to edgar-pipes!

The SEC requires a user-agent for API requests.
Please provide your name and email (e.g., "John Doe john@example.com"):
> Your Name your.email@example.com

✓ Configuration saved to ~/.config/edgar-pipes/config.toml
  You can edit this file anytime to change settings.
  Use 'ep config show' to view current configuration.
```

This is a one-time setup. You can view or modify your configuration anytime:

```bash
# View current configuration
ep config show

# Edit configuration file directly
nano ~/.config/edgar-pipes/config.toml
```

### Working with Workspaces

edgar-pipes uses workspaces to organize your analysis. A workspace is configured via a `.ft.toml` file that edgar-pipes automatically discovers by walking up the directory tree from your current location.

```bash
# Create workspace directory
mkdir aapl && cd aapl

# Create .ft.toml configuration
cat > .ft.toml <<EOF
[workspace]
ticker = "AAPL"  # Optional: default ticker

[edgar-pipes]
database = "store.db"
journals = "journals"
EOF

# Start working - edgar-pipes finds .ft.toml automatically
ep probe filings -t AAPL  # Creates store.db
ep -j new role -t AAPL -n balance -p 'PATTERN'  # Creates journals/default.jsonl
```

Typical directory structure:
```
aapl/
  .ft.toml          # Workspace configuration
  store.db          # SQLite database
  journals/         # Journal files
    default.jsonl
    setup.jsonl
```

**Key features:**
- Paths in `.ft.toml` are relative to the `.ft.toml` file location
- edgar-pipes finds `.ft.toml` by walking up from current directory
- Workspace root propagates through pipelines automatically
- Optional default ticker simplifies repetitive commands
- `.ft.toml` can be version-controlled for reproducible workflows

### Workflows

#### New company setup

When analyzing a new company for the first time without any pre-existing
references, follow this process:

```bash
# 1. Discover what filings are available for a given company, identified by its ticker
ep probe filings -t <TICKER>

# 2. Explore role names included in the selected filings
ep select filings -t <TICKER> | ep probe roles

# 3. Create group (container for role and concept patterns)
# A group typically contains one role pattern and many concept patterns
# Groups can be created before patterns are defined
ep new group Balance

# 4. Find role pattern by filtering role names
# The number of roles in any filing is typically in the hundreds
# Start with a broad pattern to see what matches (use (?i) for case-insensitive matching)
ep select filings -t <TICKER> | ep select roles -p '(?i).*balance.*' --cols role_name --uniq

# 5. Once you've identified the right pattern, create a named role-pattern
# This pattern will match role URIs across all filings and can be shared across related groups
ep new role -t <TICKER> -n balance -p '<REFINED_REGEX>'

# 6. Link the role pattern to your group
# Role names are not unique across companies, so --ticker is needed to disambiguate
ep add role -t <TICKER> -n balance -g Balance

# 7. Import concepts from the matched roles into local database
# All operations retrieving data via EDGAR public API use the probe command
ep select filings -t <TICKER> | ep select roles -g Balance | ep probe concepts

# 8. Inspect concept tags to identify patterns
# View all unique concept tags across matching filing-roles
ep select filings -t <TICKER> | ep select roles -g Balance | ep select concepts -c tag -u

# Check pattern coverage by identifying gaps (filing-roles missing specific
# concepts) using option -m. Empty result means full coverage; any rows indicate
# the pattern needs refinement or the concept doesn't appear consistently across
# all filings.
ep select filings -t <TICKER> | ep select roles -g Balance | ep select concepts -p '(?i)Cash' -m

# 9. Create concept patterns for desired financial metrics. The option -u
# associates a "user-id" to a concept for easier reference and bulk operations.
ep new concept -t <TICKER> -n "Cash" -p "^CashAndCashEquivalents.*$" -u 1
ep new concept -t <TICKER> -n "Accounts payable" -p "^AccountsPayableCurrent$" -u 2
# ... create more concept patterns ...

# 10. Link concept patterns to group
ep add concept -t <TICKER> -g Balance -u 1 2

# 11. Extract facts into database
ep update -t <TICKER> -g Balance

# 12. Generate reports
ep report -t <TICKER> -g Balance --quarterly
```

#### Specialized groups

Derived groups share the same role patterns (data scope) but filter to specific
concepts. This enables:

- Creating detailed reports for specific sections (just Assets, just Liabilities)
- Maintaining consistency (all groups use the same filing data)
- Organizing hierarchically (from comprehensive to specific)

Concepts can be organized into groups mirroring financial statements as shown
in the conceptual map below.

```
Balance
  - Balance.Assets
      - Balance.Assets.Current
      - Balance.Assets.NonCurrent
  - Balance.Liabilities
      - Balance.Liabilities.Current
      - Balance.Liabilities.NonCurrent

Operations
  - Operations.Revenue
  - Operations.OpEx
  - Operations.NonOperating
  - Operations.PerShare

CashFlow
  - CashFlow.Operating
  - CashFlow.Investing
  - CashFlow.Financing
```

Some commands to illustrate the creation of specialized groups:

```bash
# Derive subgroups that share the same role patterns but have filtered concept
# selections

ep new group Balance.Assets --from Balance -t <TICKER> --uid 1 2 3 ... 20
ep new group Balance.Liabilities --from Balance -t <TICKER> --uid 21 22 ... 40
```

#### Updates

The initial phase of defining roles, concepts and groups for a given company is
undoubtedly the most time consuming step. However, once it is complete, updating
the database with new filings is a straightforward process, does not require
user attention and can be easily automated.

```bash
ep update -t <TICKER> --force
```

Other options are also available for updating only a specific group as shown
below, although most of the time the most convenient procedure is to update
all groups at once.

```bash
ep update -t <TICKER> -g <GROUP> --force
```

#### Journals

edgar-pipes provides explicit journaling for recording workflows. Use the `-j`
flag to record commands to journals (default or named). All commands are also
automatically recorded to system history (ephemeral, in tmp) for reference.

```bash
# Record to default journal (journals/default.jsonl)
ep -j probe filings -t AAPL
ep -j default new group Balance      # Same as -j

# Record to named journals (journals/NAME.jsonl)
ep -j setup probe filings -t AAPL
ep -j daily update -t AAPL --force

# View system history (automatic, from /tmp, cross-workspace)
ep history
ep history --limit 50
ep history --errors
ep history --pattern "probe.*AAPL"

# View workspace journals
ep journal                    # View default journal
ep journal setup              # View setup journal
ep journal daily --limit 10   # Last 10 entries from daily journal

# Replay commands from journals
ep journal replay             # Replay default journal
ep journal replay setup       # Replay setup journal
ep journal replay setup 5:10,13,15,18:22
ep journal replay daily 1,5,8

# Replay from different workspace (cd to it first - .ft.toml is auto-discovered)
cd ~/aapl
ep journal replay setup
```

#### Reports

The report command queries the existing data in the database and returns data in
tabular form using the "rich" library when presented to the terminal. Other
formats are also supported such as --csv and --json.

```bash
$ ep report -t BKE -g Balance.Assets.Current --yearly

FY    Period  Scale  Cash     Inventory  Investments.Current  Prepaids.Current  Receivables.Current
2021  FY      M      253.97   102.095    12.926               10.128            12.087
2022  FY      M      252.077  125.134    20.997               12.48             12.648
2023  FY      M      268.213  126.29     22.21                18.846            8.697
2024  FY      M      266.929  120.789    23.801               20.932            6.758

# Export multiple companies to CSV
ep --csv report -t BKE -g Balance --yearly > bke.csv
ep --csv report -t MSFT -g Balance --yearly > microsoft.csv
```

Additional examples:

```bash
# Track gross margins over time
ep report -t AEO -g Operations.Revenue --yearly

# Analyze operating cash flow components
ep report -t AEO -g CashFlow.Operating --quarterly

# Track earnings per share and dilution
ep report -t AEO -g Operations.PerShare --quarterly

# Find which concepts appear consistently
ep stats concepts -t AEO -g Balance --limit 20
```

## Commands Overview

More commands are available with edgar-pipes. For additional information and
examples, refer to each command help section, e.g. "ep delete -h".

| Command   | Purpose |
|-----------|---------|
| `probe`   | Discover and cache filings, roles, concepts |
| `add`     | Link role and concepts to groups |
| `new`     | Create groups and patterns |
| `select`  | Query entities, filings, patterns |
| `update`  | Extract facts into database |
| `report`  | Generate financial reports |
| `calc`    | Perform calculations on data |
| `stats`   | Analyze concept frequency |
| `modify`  | Update patterns and manage group membership |
| `delete`  | Remove data from database |
| `config`  | Manage configuration settings |
| `journal` | View or replay workspace journals |
| `history` | View system-wide command history (ephemeral, from /tmp) |

## Requirements

- **Platform**: Linux, macOS, or WSL (Windows not supported)
- **Python**: 3.11 or higher
- **Arelle**: XBRL library (automatically installed)

edgar-pipes is designed around Unix pipes and shell scripting. Native Windows
is not supported.

## Contributing

This has been a solo project until now, and contributions are welcome! The
Author is looking for interested Community members to engage in the discussion
of new ideas. If you see something that could be done better, please share your
insight. Open an issue to discuss ideas, or submit a pull request. Fresh
perspectives are invaluable.

## Known Limitations

- **US companies only** - Currently supports Form 10-Q/10-K (US GAAP)
- **Consolidated facts only** - Extracts only entity-level consolidated data;
  segment/dimensional data (business units, geographic regions, product lines)
  is not yet supported
- **Solo development** - This started as a solo project, needs a lot of help
  for such a complex task

## Roadmap

Planned features and enhancements (in no particular order):

**Data Extraction:**
- Dimensional data support (member attributes, axes, segments)
- Support for international filers (20-F)
- Textual data extraction from 10-K/10-Q (MD&A, Risk Factors, footnotes)
- Additional filing types (8-K, DEF 14A, Form 4)

**Analysis & Integration:**
- Insider trading transaction tracking (Form 4 analysis)
- Institutional holdings monitoring (13F filings)
- MCP Server for AI agent integration

**Community:**
- Community pattern library (share role/concept patterns across users)

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Author

Created by emifrn

## Developer Documentation

Comprehensive documentation for contributors and developers:

- **[Architecture Overview](docs/developers/architecture.md)** - System design and component layers
- **[Module Documentation](docs/developers/modules/)** - Detailed docs for each module:
  - [Main & Pipeline](docs/developers/modules/main_and_pipeline.md) - Entry point and command composition
  - [CLI](docs/developers/modules/cli.md) - Command modules and utilities
  - [Cache](docs/developers/modules/cache.md) - Smart resolution layer
  - [Config](docs/developers/modules/config.md) - Configuration management
  - [Database](docs/developers/modules/db.md) - Storage layer and queries
  - [XBRL](docs/developers/modules/xbrl.md) - SEC API and XBRL parsing
- **[Design Decisions](docs/developers/decisions/)** - Rationale behind key architectural choices
- **[Examples](docs/examples/)** - Sample workflows and journal files

Journals are stored in JSONL format for easy parsing and analysis. See
[docs/examples/journal-aeo.jsonl](docs/examples/journal-aeo.jsonl) for a
complete workflow example.

## Support

- **Issues**: [GitHub Issues](https://github.com/emifrn/edgar-pipes/issues)
- **Discussions**: [GitHub Discussions](https://github.com/emifrn/edgar-pipes/discussions)
- **Documentation**: [docs/](docs/)

---

**Note**: This is alpha software. Expect rough edges. Feedback and
contributions welcome!
