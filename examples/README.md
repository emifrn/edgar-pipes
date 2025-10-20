# edgar-pipes Examples

This directory contains real-world examples of using edgar-pipes to analyze financial data.

## Example Journal: American Eagle Outfitters (AEO)

The `journal-aeo.txt` file contains a complete analysis workflow for American
Eagle Outfitters (ticker: AEO), demonstrating the progressive discovery
approach from initial filing exploration to complete financial statement
extraction.

### What's Included

The journal shows the full progression:

1. **Initial Discovery** (entries 1-3)
   - Probing filings to discover available 10-Q/10-K forms
   - Exploring roles (financial statement types)
   - Examining concepts (financial metrics) in the balance sheet

2. **Balance Sheet Setup** (entries 4-58)
   - Creating the `Balance` group
   - Defining role patterns for balance sheet identification
   - Creating 45 concept patterns for:
     - Current and non-current assets
     - Current and non-current liabilities
     - Stockholders' equity components
   - Organizing into hierarchical subgroups:
     - `Balance.Assets.Current`
     - `Balance.Assets.NonCurrent`
     - `Balance.Liabilities.Current`
     - `Balance.Liabilities.NonCurrent`

3. **Income Statement Setup** (entries 59-90)
   - Creating the `Operations` group
   - Defining role patterns for income statement
   - Creating patterns for:
     - Revenue and cost of sales
     - Operating expenses and income
     - Non-operating items
     - Earnings per share (basic and diluted)
     - Weighted average shares

4. **Equity Statement Setup** (entries 63-75)
   - Creating the `Equity` group
   - Patterns for changes in stockholders' equity:
     - Net income
     - Dividends
     - Stock compensation
     - Treasury stock transactions
     - Other comprehensive income

5. **Cash Flow Statement Setup** (entries 92-106)
   - Creating the `CashFlow` group
   - Patterns for all cash flow activities:
     - Operating activities (including adjustments)
     - Investing activities (CapEx)
     - Financing activities (buybacks, dividends)
     - Net change in cash

6. **Data Extraction** (entries 91, 106)
   - Running `update` command to extract all facts into the database

### How to Use This Example

#### Option 1: Examine the Journal

Simply read through `journal-aeo.txt` to understand the workflow. Each line shows:
- Index number
- Date and time
- Status (✓ for success, ✗ for error)
- The command that was executed

#### Option 2: Replay the Journal

You can replay the entire workflow to build the same analysis for AEO:

```bash
# Copy the example journal to your journals directory
cp examples/journal-aeo.txt ~/.config/edgar/

# Switch to the aeo journal
ep journal use aeo

# Replay all commands (WARNING: This will download filings and create database entries)
ep journal replay

# Or replay specific sections:
ep journal replay 1-10    # Just the initial discovery
ep journal replay 4-58    # Balance sheet setup
ep journal replay 59-90   # Income statement setup
```

**Note**: The replay will:
- Download XBRL filings from SEC EDGAR (~100MB for AEO)
- Create patterns and groups in your database
- Extract facts into your local SQLite database
- Take several minutes to complete

#### Option 3: Use as a Template

Adapt the pattern definitions for your own company analysis:

1. Start with `ep add -t <YOUR_TICKER> "Company Name"`
2. Use the journal as a reference for which concepts to extract
3. Adjust regex patterns to match your company's specific concept names
4. Build your own hierarchical group structure

### Key Concepts Demonstrated

- **Progressive Discovery**: Start by exploring what exists before defining patterns
- **Pattern-Based Matching**: Use regex to handle taxonomy changes and variations
- **Group Hierarchy**: Organize concepts into logical financial statement groups
- **User IDs**: Numeric IDs for easy reference and filtering
- **Derivation**: Create subgroups from parent groups using `--from` and filters
- **Pipeline Commands**: Chain commands together to explore data

### Learn More

- [Getting Started Guide](../docs/getting-started.md)
- [Researching a Company](../docs/researching-a-company.md)
- [Understanding Groups](../docs/groups.md)
- [Command Reference](../docs/commands/)

---

**Tip**: The journal system is one of edgar-pipes's most powerful features. It
automatically tracks your work, allows you to experiment freely, and makes it
easy to reproduce analyses or share workflows with others.
