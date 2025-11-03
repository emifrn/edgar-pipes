# edgar-pipes

**Extract and analyze financial data from SEC EDGAR filings using a progressive discovery process.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

## What is edgar-pipes?

edgar-pipes (ep) is a CLI tool for extracting financial data from SEC EDGAR
filings. The command fetches companies' filing information and automatically
stores it in a local SQLite3 database for persistence and fast retrieval. It
uses the EDGAR API and leverages Arelle, an open-source XBRL library, for the
extraction of selected financial data.

The command is designed to operate with Linux pipes ('|'), where the output of
a subcommand becomes the input of the next one. This mechanism enables
composable and highly adaptable data-pipelines with zero programming
requirements. This approach shifts the focus from building software for
financial data extraction to a more interactive exploration of financial
information directly in the Linux terminal, and so enabling all kinds of
analysis and reporting solutions.

The typical edgar-pipes workflow includes subcommands that **probe** XBRL
filings via EDGAR API. **Select** tags with their historical variations via
pattern matching across filings. Create **new** user defined groups that stay
consistent over time and across filings. **Update** a local SQLite3 database
with the latest XBRL facts, and **report** financial data based on previously
defined groups, e.g. 'Balance', 'Balance.Assets', 'Balance.Assets.Current',
'Operations', 'CashFlow', etc. etc. 

### Reproducible workflows

The ep command comes with a journaling system that automatically tracks command
sessions. The journaling system can be suspended, redirected to new journals,
and replayed fully or partially via indexing syntax. Journals can be used as
templates for new company analysis, as a compact backup system (storing
commands instead of data), or they can be used as part of shareable company
libraries

In short, edgar-pipes enables a progressive discovery workflow that allows
users to:

1. **Discover** what data exists in filings interactively
2. **Select** filings, roles and concepts they care about
3. **Extract** financial facts into a local database with incremental updates
4. **Report** tabular data from local database in the preferred format
5. **Update** with latest facts as they become available with new Company filings


## Why edgar-pipes?

The XBRL system is vast and complex by design. It must accommodate thousands of
companies with unique business models and reporting needs. XBRL filings contain
thousands of concepts with inconsistent naming over time and across companies.
This flexibility means analysts face a choice: manually investigate every
naming inconsistency across filings, or limit analysis to generic,
pre-structured fields.

## Key Concepts

edgar-pipes uses a three-layer architecture for organizing financial data:

### Roles

Define **where** to look in XBRL filings (which sections to examine). In XBRL
documents, presentation roles (also called role URIs or networks) organize
financial data into sections like balance sheets, income statements, cash flow
statements and many more. Each role has a URI identifier such as
`http://company.com/role/ConsolidatedBalanceSheets`. However, role URIs often
change between filings—even for the same company—as reporting structures are
refined. 

A role in edgar-pipes consists of:

- **name**: A semantic label (e.g., "Balance Sheet")
- **pattern**: A regex that matches role URIs (e.g., `".*BalanceSheet.*"`)

Pattern matching ensures data extraction remains consistent across time,
enabling reliable historical tracking without manual intervention.

Role patterns are:

- Shared across multiple groups (Balance, Balance.Assets, Balance.Liabilities)
- Company-specific

### Concepts

Define **what** to extract (which financial metrics). In XBRL, concepts are
the fundamental data elements that represent financial line items like
"CashAndCashEquivalentsAtCarryingValue", "RevenueFromContractWithCustomerExcludingAssessedTax",
or "AccountsPayableCurrent". Each concept has a tag name from a taxonomy
(typically US GAAP) that identifies what the number represents.

However, concept tags frequently change between companies reporting similar
items. For example, "Cash" might appear as `CashAndCashEquivalents`,
`CashAndCashEquivalentsAtCarryingValue`, or
`CashCashEquivalentsAndShortTermInvestments` depending on the taxonomy version
and company choice.

A concept pattern in edgar-pipes consists of:

- **name**: A semantic label meaningful to you (e.g., "Cash", "Revenue")
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
reporting. When you run `ep update -g Balance`, edgar-pipes extracts facts
matching that group's role and concept patterns.


## Quick Start

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

### Working with Multiple Databases

edgar-pipes supports multiple databases for different projects or testing. You
can switch databases at three levels:

```bash
# Single command (most temporary)
ep --db /tmp/test.db probe filings -t AAPL

# Current shell session (for pipelines)
export EDGAR_PIPES_DB_PATH=/tmp/test.db
ep probe filings -t AAPL
ep select filings -t AAPL | ep probe roles

# Permanent (all sessions)
# Edit ~/.config/edgar-pipes/config.toml:
# [database]
# path = "/path/to/your/database.db"
```

This is useful for separating production data from experiments, or maintaining
separate databases for different analysis projects.

### Workflows

#### New company setup

When analyzing a new company for the first time without any pre-existing
references, follow this process:

```bash
# Discover what filings are available
ep probe filings -t <TICKER>

# Explore role names included in the selected filings
ep select filings -t <TICKER> | ep probe roles

# The number of roles for any filing is typically several hundreds.
# Define REGEX pattern matching the correct roles across all filings.
select filings -t <TICKER> | ep select roles -p <REGEX> --cols role_name --uniq --ignore-case

# Create a role pattern to define the data scope
# This pattern will be shared across related groups
ep new role -t <TICKER> -n <NAME> -p <REGEX> 

# Create a group and link it to the role pattern by name
ep new group Balance
ep add role -g Balance -t <TICKER> -n <NAME>

# Probe what concepts are available in the group's roles
ep select filings -t <TICKER> | ep select roles -g Balance | ep probe concepts

# Inspect concept tags to find patterns
ep select filings -t <TICKER> | ep select roles -g Balance | \
ep --table select concepts --cols tag | sort | uniq | grep -v tag

# Create patterns for the desired financial metrics
ep new concept -t <TICKER> -n "Accounts payable" -p "^AccountsPayableCurrent$" -u 1
ep new concept -t <TICKER> -n "Cash" -p "^CashAndCashEquivalents.*$" -u 2
# ... create more concept patterns ...

# Link concept patterns to the desired groups
ep add concept -t <TICKER> -g Balance -u 1 2

# Extract facts into database
ep update -t <TICKER> -g Balance

# Generate reports
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

edgar-pipes automatically tracks commands in the active journal. Various
commands enable silencing, switching and replaying journals. This mechanism
is useful for reproducing workflows, regenerating databases, adapting workflows
for new companies, and sharing analysis. Below are a few command examples:


```bash
# List available journals
ep journal list

# View current journal entries
ep journal current

# Replay all commands from a journal
ep journal replay

# Replay specific commands 
ep journal replay 5-10,13,15,18-22

# Switch to a different journal
ep journal use <JOURNAL_NAME>

# Return to default journal
ep journal use

# Journals can be inspected with the command history
ep history
```

#### Reports

The report command queries the existing data in the database and returns data in
tabular form using the "rich" library when presented to the terminal. Other
formats are also supported such as --csv and --json.

```bash
$ ep report -t AAPL -g Operations.Revenue --yearly

fiscal_year  fiscal_period  Revenue      Cost of sales  Gross profit
2020         FY             274515000000 169559000000   104956000000
2021         FY             365817000000 212981000000   152836000000
2022         FY             394328000000 223546000000   170782000000
2023         FY             383285000000 214137000000   169148000000

# Export multiple companies to CSV
ep --csv report -t AAPL -g Balance --yearly > apple.csv
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

\newpage

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
| `modify`  | Update existing patterns |
| `delete`  | Remove data from database |
| `config`  | Manage configuration settings |
| `journal` | Track command history |
| `history` | View command session history |


## Requirements

- **Platform**: Linux, macOS, or WSL (Windows not supported)
- **Python**: 3.11 or higher
- **Arelle**: XBRL library (automatically installed)

edgar-pipes is designed around Unix pipes and shell scripting. Native Windows
is not supported.

\newpage

## Contributing

This has been a solo project until now, and contributions are welcome! The
Author is looking for interested Community members to engage in the discussion
of new ideas.

**Especially valuable:**

- **Design feedback** - Challenge assumptions, suggest architectural improvements
- **Ideas and use cases** - Share how you'd want to use this tool, what's missing
- **Journal library** - Share journals for different companies/industries
- **Validation** - Cross-check data against known sources
- **Documentation** - Tutorials, examples, use cases
- **Debugging** - Fix bugs, edge cases, testing
- **Features** - New commands, output formats, analyses

If you see something that could be done better, please share your insight. Open
an issue to discuss ideas, or submit a pull request. Fresh perspectives are
invaluable.

## Known Limitations

- **US companies only** - Currently supports Form 10-Q/10-K (US GAAP)
- **Consolidated facts only** - Extracts only entity-level consolidated data;
  segment/dimensional data (business units, geographic regions, product lines)
  is not yet supported
- **Solo development** - This started as a solo project, needs a lot of help
  for such a complex task

## Roadmap

Ideas for future development and up for discussion

### v0.2.0 (Future)
- Dimensional data support
- Support for international filers (20-F)
- Community pattern library

### v0.3.0 (Future)
- Textual data extraction from 10-K/10-Q (MD&A, Risk Factors, footnotes)
- MCP Server for AI agent integration

### v0.4.0 (Future)
- Additional filing types (8-K, DEF 14A, Form 4)
- Insider trading transaction tracking (Form 4 analysis)
- Institutional holdings monitoring (13F filings)

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

Journals are stored in JSONL format for easy parsing and analysis. See [docs/examples/journal-aeo.jsonl](docs/examples/journal-aeo.jsonl) for a complete workflow example.

## Support

- **Issues**: [GitHub Issues](https://github.com/emifrn/edgar-pipes/issues)
- **Discussions**: [GitHub Discussions](https://github.com/emifrn/edgar-pipes/discussions)
- **Documentation**: [docs/](docs/)

---

**Note**: This is alpha software (v0.1.0). Expect rough edges. Feedback and
contributions welcome!
