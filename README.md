# edgar-pipes

**Pattern-based financial data extraction from SEC EDGAR filings.**

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

XBRL financial data varies in structure: role URIs and concept tags differ
between companies and change over time as reporting practices evolve.
edgar-pipes addresses this through progressive discovery and pattern matching -
users explore actual role names and concept tags in their filings, then define
regex patterns that map variations to consistent semantic labels. Patterns are
defined in a declarative `ep.toml` configuration file.

The workflow begins with workspace initialization, which creates `ep.toml` and
builds a database containing filing information and role names. Users then
explore interactively: selecting roles matching their semantic intent (e.g.,
"balance sheet"), probing concepts within those roles to identify financial
metrics they want to track. Role and concept patterns are bundled into groups
in `ep.toml`. The update command extracts facts matching these patterns,
creating stable semantic datasets that remain consistent as XBRL taxonomies
evolve.

The `ep.toml` file serves as the foundation for reproducible financial
analysis. It captures the pattern definitions that users develop through
exploration, making their extraction logic explicit, shareable, and
version-controllable. Once defined, this configuration becomes the basis for
building databases: users can recreate their analysis environment or share it
with others. As new filings become available, a simple update command refreshes
the database using the established patterns, maintaining consistent semantic
groups across growing datasets.


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

Groups are the unit of extraction. The `ep build` command syncs patterns from
`ep.toml` to the database, and `ep update` extracts facts matching each group's
role and concept patterns.


## Getting Started

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
- No concepts yet (discovered through exploration)
- No groups yet (defined after pattern identification)
- No facts yet (extracted once patterns are defined)

Users are now ready to explore roles and concepts through the progressive
discovery workflow, mapping their findings into `ep.toml` patterns.

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

# Edit ep.toml to add concept patterns
# [concepts.Cash]
# uid = 1
# pattern = "^CashAndCashEquivalents.*$"
#
# [concepts."Total assets"]
# uid = 2
# pattern = "^Assets$"
```

### Define Groups

Once role and concept patterns are identified, bundle them into groups in
`ep.toml`. Groups organize which concepts to extract from which roles:

```toml
# Main group linking role and concepts
[groups.Balance]
role = "balance"
concepts = [1, 2, 3, 4, 5]

# Derived groups (inherit role from parent, filter concepts)
[groups."Balance.Assets"]
from = "Balance"
concepts = [1, 2]
```

### Extract Facts

With groups defined in `ep.toml`, use `ep build` to sync the patterns to the
database. Then use `ep update` to fetch facts from SEC filings. The update
command downloads XBRL files, matches roles and concepts according to the
patterns in each group, and imports the associated facts into the database.
When no specific group is specified, all defined groups are processed.

```bash
# Sync patterns from ep.toml to database
ep build

# Fetch facts from SEC for all groups
ep update

# Fetch facts for specific group
ep update -g Balance
```

### Generate Reports

Once facts are downloaded to the local SQLite3 database, users can generate
financial reports from the extracted data.

```bash
# Generate quarterly report
ep report -g Balance --quarterly

# Generate annual report
ep report -g Operations --yearly
```

**New to edgar-pipes?** See [HOWTO.md](HOWTO.md) for practical workflow guide.

## Requirements

- **Platform**: Linux, macOS, or WSL (Windows not supported)
- **Python**: 3.11 or higher
- **Arelle**: XBRL library (automatically installed)

edgar-pipes is designed around Unix pipes and shell scripting. Native Windows
is not supported.

## Known Limitations

- **US companies only** - Currently supports Form 10-Q/10-K (US GAAP)
- **Consolidated facts only** - Extracts only entity-level consolidated data;
  segment/dimensional data (business units, geographic regions, product lines)
  is not yet supported

## Contributing

This has been a solo project until now, and contributions are welcome! The
Author is looking for interested Community members to engage in the discussion
of new ideas. If you see something that could be done better, please share your
insight. Open an issue to discuss ideas, or submit a pull request. Fresh
perspectives are invaluable.

## Documentation

- **[HOWTO.md](HOWTO.md)** - Practical workflow guide
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Coding conventions
- **[Architecture](docs/developers/architecture.md)** - System design for contributors

## Support

- **Issues**: [GitHub Issues](https://github.com/emifrn/edgar-pipes/issues)
- **Discussions**: [GitHub Discussions](https://github.com/emifrn/edgar-pipes/discussions)

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

**Note**: This is alpha software. Expect rough edges. Feedback and
contributions welcome!
