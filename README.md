# edgar-pipes - Progressive XBRL Financial Data Extraction

**Extract and analyze financial data from SEC EDGAR filings using progressive discovery and pattern matching.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## What is edgar-pipes?

edgar-pipes is a CLI tool for extracting financial data from SEC EDGAR XBRL filings. Unlike traditional approaches that force you to navigate complex XBRL taxonomies, edgar-pipes uses **progressive discovery** to help you:

1. **Discover** what data exists in filings
2. **Define patterns** that match the concepts you care about
3. **Extract facts** into a local database
4. **Generate reports** in your preferred format

## Why edgar-pipes?

### The Problem

XBRL filings contain thousands of concepts with inconsistent naming:
- Revenue might be called `RevenueFromContractWithCustomer`, `SalesRevenue`, or `Revenues`
- Concept names change across taxonomy versions (us-gaap/2023 vs us-gaap/2024)
- Each company has unique reporting structures

Traditional tools either:
- Give you raw XBRL (overwhelming complexity)
- Pre-normalize data (black box, limited flexibility)
- Cost thousands per year (Bloomberg, FactSet)

### The Solution

edgar-pipes lets you:
- **Explore before extracting** - See what's actually in the filings
- **Define semantic patterns** - Map company-specific concepts to your own names
- **Build reusable groups** - Create Balance, Operations, CashFlow templates
- **Extract on demand** - Pull only the data you need
- **Verify sources** - Every number traces back to specific SEC filings

## Key Features

- **Progressive Discovery Workflow** - Probe → Pattern → Extract → Report
- **Pattern-Based Concept Matching** - Handle taxonomy changes automatically
- **Group Hierarchy** - Organize concepts by financial statement
- **Pipeline Architecture** - Compose commands with Unix pipes
- **Multiple Output Formats** - Table, JSON, CSV
- **Quarterly Derivation** - Automatically calculate Q4 from FY and YTD data
- **Statistical Analysis** - Analyze concept frequency across filings
- **Local SQLite Database** - Fast, portable, no external dependencies
- **Journal System** - Track and replay your analysis workflows

## Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/emifrn/edgar-pipes.git
cd edgar-pipes

# Install package
pip install -e .
```

### Basic Workflow

```bash
# 1. Add a company
ep add -t AAPL "Apple Inc"

# 2. Discover available filings
ep probe filings -t AAPL

# 3. Explore what's in the filings
ep probe roles -t AAPL
ep select filings -t AAPL | probe concepts

# 4. Create patterns and groups
ep new group Balance
ep new concept -t AAPL -n "Cash" -p "^CashAndCashEquivalents.*$" -u 1
ep new role -t AAPL -p ".*BalanceSheet.*" -u 1

# 5. Link patterns to groups
ep add concept -g Balance -t AAPL -u 1
ep add role -g Balance -t AAPL -u 1

# 6. Extract data
ep update -t AAPL -g Balance

# 7. Generate report
ep report -t AAPL -g Balance --yearly
```

### Example Output

```bash
$ ep report -t AAPL -g Operations.Revenue --yearly

fiscal_year  fiscal_period  Revenue      Cost of sales  Gross profit
2020         FY             274515000000 169559000000   104956000000
2021         FY             365817000000 212981000000   152836000000
2022         FY             394328000000 223546000000   170782000000
2023         FY             383285000000 214137000000   169148000000
```

### Using Journal System

edgar-pipes automatically tracks all commands you run. You can replay entire analysis workflows:

```bash
# List available journals
ep journal list

# View current journal entries
ep journal current

# Replay all commands from a journal
ep journal replay

# Replay specific commands (e.g., entries 5-10)
ep journal replay 5-10

# Switch to a different journal
ep journal use myanalysis
```

**Included Example**: The repository includes a complete example journal in the `examples/` directory showing a real workflow for American Eagle Outfitters (AEO), including:
- Balance sheet extraction with hierarchical groups (Assets, Liabilities)
- Income statement patterns (Revenue, OpEx, EPS)
- Cash flow statement (Operating, Investing, Financing activities)
- Equity statement patterns

See [examples/README.md](examples/README.md) for details on examining and replaying this workflow.

## Core Concepts

### Progressive Discovery

edgar-pipes follows a progressive workflow:

```
Probe → Pattern → Extract → Report
  ↓        ↓         ↓         ↓
Explore  Define    Store    Analyze
```

You start by exploring what exists, then progressively refine what you extract.

### Pattern-Based Matching

Instead of hardcoding concept names, you define patterns:

```bash
# Create pattern that matches revenue across taxonomy versions
ep new concept -t AAPL -n "Revenue" \
  -p "^RevenueFromContractWithCustomerExcludingAssessedTax$" -u 1
ep add concept -g Operations -t AAPL -u 1
```

Patterns handle:
- Taxonomy version changes (us-gaap/2023 → us-gaap/2024)
- Company-specific naming variations
- Multiple concepts matching to a single semantic name

### Group Hierarchy

Organize concepts into groups mirroring financial statements:

```
Balance
├── Balance.Assets
│   ├── Balance.Assets.Current
│   └── Balance.Assets.NonCurrent
└── Balance.Liabilities
    ├── Balance.Liabilities.Current
    └── Balance.Liabilities.NonCurrent

Operations
├── Operations.Revenue
├── Operations.OpEx
├── Operations.NonOperating
└── Operations.PerShare

CashFlow
├── CashFlow.Operating
├── CashFlow.Investing
└── CashFlow.Financing
```

### Pipeline Composition

Commands compose via pipes:

```bash
# Select roles matching a pattern, then analyze concept frequency
ep select roles -t AAPL -p ".*BalanceSheet.*" | ep stats concepts

# Export multiple companies to CSV
ep report -t AAPL -g Balance --yearly --csv > apple.csv
ep report -t MSFT -g Balance --yearly --csv > microsoft.csv
```

## Commands Overview

| Command | Purpose |
|---------|---------|
| `add` | Register companies by ticker |
| `probe` | Discover filings, roles, concepts |
| `new` | Create groups and patterns |
| `select` | Query entities, filings, patterns |
| `update` | Extract facts into database |
| `report` | Generate financial reports |
| `calc` | Perform calculations on data |
| `stats` | Analyze concept frequency |
| `group` | Organize patterns into groups |
| `modify` | Update existing patterns |
| `delete` | Remove data from database |
| `journal` | Track command history |
| `summary` | View extraction progress |

## Documentation

- [Getting Started Guide](docs/getting-started.md)
- [Researching a Company](docs/researching-a-company.md)
- [Understanding Groups](docs/groups.md)
- [Command Reference](docs/commands/)
- [Architecture Overview](docs/architecture.md)

## Real-World Use Cases

### Margin Analysis
```bash
# Track gross margins over time
ep report -t AEO -g Operations.Revenue --yearly
# Analyze Revenue, COGS, Gross Profit trends
```

### Cash Flow Trends
```bash
# Analyze operating cash flow components
ep report -t AEO -g CashFlow.Operating --quarterly
# See D&A, stock comp, deferred tax impact
```

### EPS Analysis
```bash
# Track earnings per share and dilution
ep report -t AEO -g Operations.PerShare --quarterly
# Monitor EPS basic, diluted, share counts
```

### Concept Frequency
```bash
# Find which concepts appear consistently
ep stats concepts -t AEO -g Balance --limit 20
# Identify reporting changes over time
```

## Technical Highlights

### Quarterly Data Derivation

edgar-pipes automatically derives Q4 data:
- **Stock variables** (balance sheet): Q4 = FY value
- **Flow variables** (income/cash flow): Q4 = FY - 9M YTD

This handles the common filing pattern: Q1 + 9M YTD + FY

### Taxonomy Version Handling

edgar-pipes matches concepts by tag name (not CID) to handle taxonomy changes:
- us-gaap/2023: `NetIncome` has CID 1234
- us-gaap/2024: `NetIncome` has CID 5678
- edgar-pipes: Matches by tag, not CID ✓

### Period Mode Intelligence

edgar-pipes interprets period modes correctly:
- `quarter` → Q1, Q2, Q3 (standalone quarters)
- `threeQ` → 9M YTD (NOT Q3 quarter!)
- `semester` → 6M YTD
- `year` → FY
- `instant` → Point-in-time (balance sheet)

## Requirements

- Python 3.10 or higher
- SQLite (included with Python)
- Internet connection (for downloading filings)

No external dependencies required - uses only Python standard library.

## Project Structure

```
edgar-pipes/
├── cli/          # Command-line interface modules
├── db/           # Database layer (SQLite)
├── xbrl/         # XBRL parsing logic
├── docs/         # Documentation
├── main.py       # Entry point
└── README.md     # This file
```

## Contributing

Contributions welcome! Areas where help is needed:

- **Pattern library** - Share patterns for different companies/industries
- **Validation** - Cross-check data against known sources
- **Documentation** - Tutorials, examples, use cases
- **Testing** - Unit tests, integration tests
- **Features** - New commands, output formats, analyses

Please open an issue or pull request on GitHub to contribute.

## Known Limitations

- **US companies only** - Currently supports Form 10-Q/10-K (US GAAP)
- **No automated tests** - Manual testing only (for now)
- **Limited error recovery** - Some edge cases may fail
- **Q2/Q3 cash flow gaps** - Normal SEC practice (companies don't file complete Q2/Q3 CF)

## Roadmap

### v0.2.0 (Planned)
- Pattern import/export functionality
- Community pattern library
- Data validation suite
- Basic unit tests

### v0.3.0 (Future)
- MCP Server for AI agent integration
- Cross-validation against Bloomberg/Yahoo Finance
- Performance optimizations
- Support for international filers (20-F)

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Author

Created by emifrn

## Acknowledgments

- Built with insights from analyzing hundreds of SEC EDGAR filings
- Inspired by the need for transparent, flexible financial data extraction
- Special thanks to the open-source community

## Support

- **Issues**: [GitHub Issues](https://github.com/emifrn/edgar-pipes/issues)
- **Discussions**: [GitHub Discussions](https://github.com/emifrn/edgar-pipes/discussions)
- **Documentation**: [docs/](docs/)

---

**Note**: This is alpha software (v0.1.0). Expect rough edges. Feedback and contributions welcome!
