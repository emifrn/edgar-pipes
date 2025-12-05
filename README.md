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
information directly in the Linux terminal.

edgar-pipes uses pattern matching to handle XBRL data variability: role URIs
and concept tags that change over time, vary between companies, and evolve with
new accounting standards. Patterns are defined in a declarative `ep.toml`
configuration file that is human-readable and version-controllable.

The progressive discovery workflow enables users to:

1. **Initialize** workspace and build database with filing metadata
2. **Explore** available role names and concept tags interactively
3. **Define** role and concept patterns in ep.toml
4. **Build** database to extract facts matching defined patterns
5. **Report** financial data from local database


## Key Concepts

edgar-pipes uses a three-layer architecture for organizing financial data:

### Roles

Define **where** to look in XBRL filings (which sections to examine). In XBRL
documents, presentation roles organize financial data into sections like
balance sheets, income statements, and cash flow statements. Each role has a
URI identifier. However, role URIs often change between filings, even for the
same company.

A role pattern in edgar-pipes consists of:

- **name**: A user-defined semantic label (e.g., "balance")
- **pattern**: A regex that matches role URIs across filings

Pattern matching ensures data extraction remains consistent across time,
enabling reliable historical tracking.

### Concepts

Define **what** to extract (which financial metrics). In XBRL, concepts are
the fundamental data elements that represent financial line items. However,
concept tags frequently change between companies and over time as accounting
standards evolve.

A concept pattern in edgar-pipes consists of:

- **name**: A user-defined semantic label (e.g., "Cash")
- **pattern**: A regex matching concept tags
- **uid**: A user-assigned numeric ID for easy reference

Pattern matching abstracts away taxonomy variations, mapping multiple tags to a
single consistent label across time and companies.

### Groups

Groups organize patterns into cohesive datasets for extraction and reporting. A
group brings together:

- **Role patterns**: Define the data scope (which filing sections)
- **Concept patterns**: Define what to extract (which metrics)
- **Hierarchy**: Groups can derive from parent groups with filtered concepts

Groups are the unit of extraction. When you run `ep build`, edgar-pipes
extracts facts matching each group's role and concept patterns.


## Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/emifrn/edgar-pipes.git
cd edgar-pipes

# Install package (virtual environment recommended)
python -m venv edgar-env
source edgar-env/bin/activate
pip install -e .

# Verify installation
ep --help
```

Use `-e` (editable) if you want to modify the code or pull updates.

**Updating:**
```bash
cd edgar-pipes && git pull origin main
```

### Initialize and Build

```bash
# Create new workspace
mkdir mycompany && cd mycompany

# Initialize ep.toml (prompts for user-agent, ticker, cutoff date)
ep init

# Build database (fetches filings and caches role names)
ep build
```

After `ep build` completes, your database contains:
- All filings for the ticker (from cutoff date forward)
- All role names for each filing
- No facts yet (no patterns defined)

You're now ready to explore and define patterns.

### Explore and Define Patterns

```bash
# View available role names
ep select filings | ep select roles -c role_name -u

# Test a role pattern
ep select filings | ep select roles -p '(?i).*balance.*' -c role_name -u

# Edit ep.toml to add the role pattern
# [roles.balance]
# pattern = "(?i)^CONSOLIDATEDBALANCESHEETS.*$"

# Probe concepts for that role
ep select filings | ep select roles -p '(?i)^CONSOLIDATEDBALANCESHEETS' | ep probe concepts

# View concept tags
ep select filings | ep select roles -p '(?i)^CONSOLIDATEDBALANCESHEETS' | ep select concepts -c tag -u

# Edit ep.toml to add concept patterns and groups
# See docs/examples/ for complete ep.toml examples
```

### Extract Facts

```bash
# Build database with your patterns (extracts facts)
ep build

# Generate reports
ep report -g Balance --quarterly
```

**New to edgar-pipes?** See [CHEATSHEET.md](CHEATSHEET.md) for command reference.

## Working with ep.toml

All patterns are defined in the `ep.toml` configuration file. After exploring
role names and concept tags, you manually edit this file to add your patterns.

Typical workflow structure:
```
mycompany/
  ep.toml          # Configuration (edited manually)
  db/
    edgar.db       # SQLite database
```

Example ep.toml structure:

```toml
# User preferences
user_agent = "Your Name your@email.com"
ticker = "AAPL"
database = "db/edgar.db"
cutoff = "2015-01-01"

# Define role patterns
[roles.balance]
pattern = "(?i)^CONSOLIDATEDBALANCESHEETS.*$"

# Define concept patterns
[concepts.Cash]
uid = 1
pattern = "^CashAndCashEquivalents.*$"

[concepts.Revenue]
uid = 100
pattern = "^RevenueFromContractWithCustomer.*$"

# Define groups linking roles and concepts
[groups.Balance]
role = "balance"
concepts = [1]

# Derived groups (inherit role from parent)
[groups."Balance.Assets"]
from = "Balance"
concepts = [1]
```

See [docs/examples/](docs/examples/) for complete ep.toml examples.

## Common Workflows

### Updating with New Filings

Once patterns are defined, updating is straightforward:

```bash
# Fetch latest filings and extract facts
ep build
```

The `build` command automatically:
- Fetches new filings from SEC
- Extracts facts for all groups
- Updates existing facts if taxonomy changed

### Reporting

```bash
# Generate quarterly report
ep report -g Balance --quarterly

# Export to CSV
ep report -g Balance --yearly --csv > output.csv

# View specific derived group
ep report -g Balance.Assets.Current --yearly
```

### Hierarchical Groups

Groups can derive from parent groups to create focused reports:

```toml
[groups.Balance]
role = "balance"
concepts = [1, 2, 3, 4, 5, 6]  # All balance sheet items

[groups."Balance.Assets"]
from = "Balance"
concepts = [1, 2, 3]  # Just assets

[groups."Balance.Liabilities"]
from = "Balance"
concepts = [4, 5, 6]  # Just liabilities
```

Derived groups share the parent's role pattern but filter concepts.

## Commands Overview

| Command   | Purpose |
|-----------|---------|
| `init`    | Initialize workspace with ep.toml |
| `build`   | Fetch filings, cache roles, extract facts |
| `select`  | Query filings, roles, concepts, groups |
| `probe`   | Cache concepts for specific filing-roles |
| `report`  | Generate financial reports |
| `stats`   | Analyze concept frequency |
| `modify`  | Update patterns in database |
| `delete`  | Remove data from database |

Run `ep <command> -h` for detailed help on each command.

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

## Documentation

- **[CHEATSHEET.md](CHEATSHEET.md)** - Quick command reference
- **[Architecture](docs/developers/architecture.md)** - System design for contributors

## Support

- **Issues**: [GitHub Issues](https://github.com/emifrn/edgar-pipes/issues)
- **Discussions**: [GitHub Discussions](https://github.com/emifrn/edgar-pipes/discussions)

---

**Note**: This is alpha software. Expect rough edges. Feedback and
contributions welcome!
