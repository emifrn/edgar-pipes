# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-01-XX

### Added

#### Core Functionality
- Complete progressive discovery workflow for XBRL financial data extraction
- 13 CLI commands covering full analysis lifecycle
- SQLite-backed persistent storage with efficient schema
- Pipeline architecture enabling command composition via Unix pipes
- Journal system for tracking and replaying analysis workflows

#### Commands
- **add**: Register companies by ticker symbol
- **probe**: Discover filings, roles, and concepts in XBRL documents
- **new**: Create concept groups and patterns with flexible filtering
- **select**: Query entities, filings, roles, concepts, and patterns
- **update**: Extract facts from filings into local database
- **report**: Generate financial reports with period pivoting
- **calc**: Perform calculations on extracted data
- **stats**: Analyze concept frequency across filings
- **group**: Organize patterns into hierarchical groups
- **modify**: Update existing patterns and groups
- **delete**: Remove data from database with cascading deletes
- **journal**: View and export command history
- **summary**: View extraction progress and coverage

#### Financial Statement Groups
- **Balance Sheet** with hierarchical subgroups:
  - Balance.Assets (Current, NonCurrent)
  - Balance.Liabilities (Current, NonCurrent)
- **Income Statement** with focused subgroups:
  - Operations.Revenue (margin analysis)
  - Operations.OpEx (operating efficiency)
  - Operations.NonOperating (below-the-line items)
  - Operations.PerShare (EPS and dilution metrics)
- **Cash Flow Statement** with activity-based subgroups:
  - CashFlow.Operating (cash generation)
  - CashFlow.Investing (CapEx and FCF)
  - CashFlow.Financing (shareholder returns)
- **Statement of Stockholders' Equity** (flat structure)

#### Data Processing Features
- **Quarterly derivation**: Automatic Q4 calculation from FY and 9M YTD data
- **Taxonomy version handling**: Tag-based concept matching across us-gaap versions
- **Period mode intelligence**: Correct interpretation of quarter, threeQ, semester, year, instant
- **Sparse data handling**: Proper CSV export with all unique field names
- **Pattern-based matching**: Regex patterns for flexible concept identification

#### Output Formats
- **Table format**: Formatted tables with configurable themes
- **JSON format**: Machine-readable JSONL output
- **CSV format**: Spreadsheet-compatible export
- **Pipeline format**: Internal JSON for command chaining

#### User Interface
- Multiple table themes (financial, minimal, grid, nobox variants)
- Progress indicators during extraction
- Comprehensive help system for all commands
- Clear error messages with context

#### Documentation
- Getting started guide
- Complete company research workflow guide
- Group organization documentation
- Command reference documentation
- Architecture overview
- Release planning document

### Technical Details

#### Taxonomy Handling
- Concept matching by tag name (not CID) to handle taxonomy changes
- Support for us-gaap/2018 through us-gaap/2025
- Automatic detection of instant vs period contexts

#### Quarterly Data Logic
- Q2 selection: Uses semester mode (6M YTD - Q1)
- Q3 selection: Uses threeQ mode (9M YTD - Q1)
- Q4 derivation: FY - 9M YTD for flow variables, FY value for stock variables
- Period labels: "9M YTD" (not "Q3") for threeQ mode to avoid confusion

#### Database Schema
- Efficient SQLite schema with proper indexes
- Cascading deletes for data integrity
- Row factory for dict-based results
- Support for both consolidated and dimensioned facts

#### Pattern System
- User-friendly UID system for pattern reference
- Regex-based matching with validation
- Group-based pattern organization
- Pattern inheritance for subgroups

### Known Limitations
- US companies only (Form 10-Q/10-K)
- No automated tests
- Limited error recovery in XBRL parsing
- Q2/Q3 cash flow often incomplete (normal SEC filing practice)
- No validation against external sources

### Dependencies
- Python 3.10 or higher
- SQLite (included with Python)
- Standard library only (no external packages)

---

## Future Releases

### [0.2.0] - Planned
- Pattern import/export functionality
- Community pattern library support
- Data validation suite
- Basic unit tests
- Performance optimizations

### [0.3.0] - Future
- MCP Server for AI agent integration
- Cross-validation against Bloomberg/Yahoo Finance
- Support for international filers (Form 20-F)
- Web interface (optional)
- Advanced calculation engine

---

[0.1.0]: https://github.com/emifrn/edgar-pipes/releases/tag/v0.1.0
