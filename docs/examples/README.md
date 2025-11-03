# Examples

This directory contains example workflows and tutorials demonstrating how to use
edgar-pipes for financial analysis.

## researching-a-company.md

**Complete step-by-step tutorial** for analyzing a company from scratch:
- Initial discovery and probing
- Pattern identification and analysis
- Creating groups, roles, and concept patterns
- Extracting facts and generating reports
- Troubleshooting common issues
- Advanced multi-company analysis

This is the recommended starting point for new users.

## journal-aeo.jsonl

A complete workflow showing how to analyze American Eagle Outfitters (AEO)
financial statements using edgar-pipes.

This journal demonstrates the progressive discovery and extraction pattern:

1. **Probe** - Discover and cache filings, roles, and concepts
2. **Define** - Create groups and patterns to organize financial concepts
3. **Extract** - Pull facts from XBRL filings into structured data

### What the workflow covers:

**Balance Sheet Setup (entries 1-58)**
- Probe filings for AEO and discover available roles
- Create Balance group and role patterns to match balance sheet roles
- Define 45 balance sheet concepts with regex patterns
- Organize concepts into hierarchical groups (Assets, Liabilities, Current/NonCurrent)

**Income Statement Setup (entries 59-94)**
- Create Operations group for income statement data
- Define revenue, expense, and per-share metrics
- Organize into subgroups (Revenue, OpEx, NonOperating, PerShare)

**Cash Flow Statement Setup (entries 96-113)**
- Create CashFlow group for statement of cash flows
- Define operating, investing, and financing activities
- Organize into activity subgroups

**Data Extraction (entries 95, 113)**
- Run update command to extract facts from all filings
- Data is now ready for analysis and reporting

### Key patterns demonstrated:

**Progressive refinement**: Start with broad discovery (probe filings, roles,
concepts), then progressively narrow and organize the data through groups and
patterns.

**Pattern-based extraction**: Use regex patterns to match XBRL tags across
different filings and taxonomy versions, handling variations in how companies
report the same concept.

**Hierarchical organization**: Create nested groups (e.g., Balance.Assets.Current)
to organize concepts logically for analysis and reporting.

**Reusable definitions**: Once groups and patterns are defined for one company,
they can be reused or adapted for other companies in the same industry.

### How to use:

The journal file shows the command history that built up the analysis structure.
To replicate:

1. Start with probe commands to discover data
2. Create groups to organize your analysis
3. Define role patterns to find the right sections of filings
4. Define concept patterns to extract specific line items
5. Link concepts to groups
6. Run update to extract the data
7. Use select/report commands to analyze

This iterative process lets you build a complete financial model piece by piece,
validating each step along the way.
