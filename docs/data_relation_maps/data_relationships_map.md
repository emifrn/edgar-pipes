# Edgar Data Relationships and Entity Map

## Core Entity Relationships

```
Companies (entities)
├── CIK: "0000320193" (immutable SEC identifier)
├── Ticker: "AAPL" (can change over time)
└── Name: "Apple Inc."
    │
    └── Filings (1:many)
        ├── Access Number: "0000320193-24-000007"
        ├── Form Type: "10-K", "10-Q"
        ├── Filing Date: "2024-09-28"
        └── XBRL URL: "https://sec.gov/Archives/..."
            │
            └── Filing Roles (1:many)
                ├── Role Name: "StatementConsolidatedBalanceSheets"
                ├── Role Name: "StatementOfIncome"
                └── Role Name: "StatementOfCashFlows"
                    │
                    └── Concepts (many:many via filing_role_concepts)
                        ├── Taxonomy: "http://fasb.org/us-gaap/2024"
                        ├── Tag: "CashAndCashEquivalentsAtCarryingValue"
                        ├── Name: "Cash and Cash Equivalents"
                        └── Facts (1:many)
                            ├── Value: 28999000000
                            ├── Period: "2024-09-28" (instant/quarter/year)
                            ├── Unit: "USD"
                            └── Dimensions: {} (none for consolidated)
```

## Pattern System Relationships

### Groups: Global Semantic Containers
```
Groups (global)
├── group_id: 1
├── name: "balance"
└── Purpose: Abstract semantic organization
    │
    ├── Role Patterns (many:many via group_role_patterns)
    │   ├── pattern_id: 1
    │   ├── cik: "0000320193" (company-specific)
    │   ├── pattern: "StatementConsolidatedBalanceSheets.*"
    │   └── Purpose: "Where to look for balance sheet data"
    │
    └── Concept Patterns (many:many via group_concept_patterns)
        ├── pattern_id: 1
        ├── cik: "0000320193" (company-specific)
        ├── name: "Cash" (semantic identifier)
        ├── pattern: "^CashAndCashEquivalentsAtCarryingValue$"
        └── Purpose: "What financial data to extract"
```

## Database Schema Relationships

### Core Data Tables
```sql
entities (1) ←→ (many) filings
    ↓
filings (1) ←→ (many) filing_roles
    ↓
filing_roles (many) ←→ (many) concepts via filing_role_concepts
    ↓
concepts (1) ←→ (many) facts
    ↓
facts ←→ contexts (periods)
facts ←→ units (USD, shares, etc.)
facts ←→ dimensions (segments, breakdowns)
```

### Pattern Organization Tables
```sql
-- Groups are global
groups (group_id, name)

-- Role patterns are company-specific, linked to groups
role_patterns (pattern_id, cik, pattern)
group_role_patterns (group_id, pattern_id)

-- Concept patterns are company-specific with semantic names
concept_patterns (pattern_id, cik, name, pattern)  
group_concept_patterns (group_id, pattern_id)
```

## Conceptual Flow Relationships

### Discovery Chain
```
SEC API
  ↓ probe filings
Companies → Filings
  ↓ probe roles  
Filings → XBRL Roles
  ↓ probe concepts
Roles → XBRL Concepts
  ↓ update (extract facts)
Concepts → Financial Facts
```

### Pattern Chain
```
Financial Domain Knowledge
  ↓ new group
Global Group Definition
  ↓ add roles
Company-Specific Role Patterns
  ↓ add concept  
Company-Specific Concept Patterns
  ↓ select concepts
Concept Discovery & Matching
  ↓ update
Fact Extraction
```

## Many-to-Many Relationship Details

### Group ↔ Role Pattern Relationship
```
Group "balance" can have multiple role patterns:
- "StatementConsolidatedBalanceSheets.*"
- ".*BALANCESHEETS.*" 
- "BalanceSheet$"

Role pattern "StatementConsolidatedBalanceSheets.*" can serve multiple groups:
- "balance" (comprehensive balance sheet)
- "assets" (asset-focused analysis)
- "current_assets" (current asset subset)
```

### Group ↔ Concept Pattern Relationship
```
Group "balance" can have multiple concept patterns:
- "Cash": "^CashAndCashEquivalentsAtCarryingValue$"
- "Inventory": "^InventoryNet$"
- "Assets": "^AssetsCurrent$"

Concept pattern "Cash" can serve multiple groups:
- "balance" (full balance sheet context)
- "current_assets" (liquidity analysis)
- "liquid_assets" (cash-focused analysis)
```

## Data Flow Through System

### Input Data Flow
```
SEC EDGAR API
  ↓ HTTP requests
Raw XBRL Documents
  ↓ Arelle parser
Structured XBRL Model
  ↓ Fact extraction
Numerical Facts + Context
  ↓ SQLite storage
Queryable Financial Database
```

### Query Data Flow
```
CLI Command
  ↓ Pattern matching
Group → Role Patterns → XBRL Roles
Group → Concept Patterns → XBRL Concepts
  ↓ Join operations
Role + Concept Combinations
  ↓ Fact lookup
Financial Facts with Periods
  ↓ Pipeline output
Formatted Results (table/JSON/CSV)
```

## Temporal Relationships

### Filing Timeline
```
Company Filing Schedule:
Q1 Filing (May) → Q2 Filing (August) → Q3 Filing (November) → 10-K Annual (March)
  ↓ Each filing contains:
  - Same role names (usually consistent)
  - Same concept tags (usually consistent)  
  - Different fact values and periods
  - Potential role/concept evolution over time
```

### Pattern Evolution
```
Time T1: Role pattern "StatementOfIncome.*"
Time T2: Company changes to "ConsolidatedStatementOfIncome.*"
  ↓ Pattern strategy:
  - Keep old pattern for historical data
  - Add new pattern for current data
  - Group contains both patterns for comprehensive coverage
```

## Cross-Entity Relationships

### Company-to-Company Pattern Reuse
```
Apple "balance" group patterns
  ↓ derive/copy
Microsoft "balance" group
  ↓ adapt patterns for different naming conventions
  - Apple: "StatementConsolidatedBalanceSheets"
  - Microsoft: "BalanceSheet" 
  - Same semantic intent, different technical implementation
```

### Industry Pattern Families
```
Technology Companies:
- Similar role naming conventions
- Similar concept taxonomies
- High pattern reusability

Financial Companies:  
- Different regulatory requirements
- Different concept emphasis
- Lower pattern reusability across industries
```

## Error and Missing Data Relationships

### Missing Role Patterns
```
Group "balance" + Company AAPL
  ↓ No role patterns defined
  ✗ Error: "group has no role patterns defined for AAPL"
  ↓ Resolution:
  ep add roles --ticker AAPL --group balance --pattern "..."
```

### Missing Concept Patterns  
```
Group "balance" + Role patterns exist + Company AAPL
  ↓ No concept patterns defined
  ✗ Empty results from concept queries
  ↓ Resolution:
  ep add concept --ticker AAPL --group balance --name "..." --pattern "..."
```

### Pattern Mismatch
```
Role patterns → Find XBRL roles successfully
Concept patterns → No matching concepts in those roles
  ↓ Diagnosis:
  - Concept patterns too restrictive
  - Role patterns finding wrong roles
  - Company changed naming conventions
  ↓ Resolution:
  - Broaden concept patterns
  - Adjust role patterns  
  - Add temporal variation patterns
```