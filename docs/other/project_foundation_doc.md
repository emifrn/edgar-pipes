# EDGAR CLI - Project Foundation Document

## PROJECT VISION

**Goal**: Robust CLI-driven financial analysis suite for SEC XBRL data, built around a declarative, inspectable SQLite database.

**Philosophy**: Transform complex XBRL data analysis into an intuitive, user-driven workflow for the exploration of roles, filings, and concept via iterative probing followed by automatic updating. Bridges the gap between what users think about (financial concepts like "Assets", "Revenue") and what XBRL provides (role names).

## CORE DESIGN PRINCIPLES

### **1. Functional Programming Style**
- **Pure functions preferred** over classes
- **Self-documenting code** - function names tell the story
- **Helper function pattern** - break complex operations into readable narratives
- **Immediately obvious** - code should be clear 6 months from now

### **2. Separation of Concerns**
- **Discovery vs Execution**: 
	- Probe phase = human decision-making
	- Update phase = automated execution
- **Cache layer**: Data acquisition with auto-fetching
- **Database abstraction**: All SQL isolated in `db/queries.py`
- **One responsibility per module**: Clear boundaries between XBRL, CLI, database layers

### **3. User Experience Philosophy**
- **Progressive disclosure**: Overview first, drill down for details
- **No dead ends**: Auto-discovery eliminates "not found" frustrations
- **Concept-driven**: Users search by financial concepts, not technical role names
- **Temporal awareness**: Handle role changes over time gracefully

## SYSTEM ARCHITECTURE

### **Data Flow Pipeline**
```
SEC EDGAR API → XBRL Files → Arelle Parser → Fact Extraction → SQLite → CLI Reports with Formulas
```

## KEY ARCHITECTURAL DECISIONS

### **1. Company Identity Strategy**
- **CIK** (immutable SEC identifier) is primary key internally
- **Ticker** is user-facing but can change over time (FB→META problem)
- Companies cached on first lookup, referenced by CIK thereafter
- The CIK is treated as a 10 digit STRING internally in the project. Function at the boundary fetching CIKs from Edgar need to convert potential integer CIKs to the 10 digits format.

### **2. Role-Based Fact Organization**
- Companies map to XBRL **roles** via many-to-many `company_roles` table
- Roles are user-labeled: `balance`, `income`, `cash`
- Same statement type can have different role names across companies/time
- **Temporal role mapping**: User decides which role to use for which time period

### **3. Fact Selection Logic**
- Only **consolidated** facts (no segments/dimensions for now)
- Only **presentation role** facts (avoids disclosure noise)
- **Period-aware derivation**: Q4 = FY - (Q1+Q2+Q3) when missing
- **Mode classification**: instant, quarter, semester, threeQ, year based on date ranges
- **Best fact selection** per concept/period using contextual preferences

### **4. Cache-First Architecture**
- `cache.get_companies()`: Auto-fetches company data from SEC if missing
- `cache.get_recent_filings()`: Auto-fetches filing metadata if missing
- `cache.get_xbrl_url()`: Resolves and caches XBRL file URLs
- `cache.filtered_filings()`: Reusable generator for filing filters

## USER WORKFLOW DESIGN

### **The Enhanced Discovery Process**
**Problem Solved**: XBRL models contain 600+ roles with cryptic names. Users don't know what "StatementOfFinancialPositionClassified" means, but they know they want "Assets" data.

**Solution**: Concept-driven discovery with bidirectional exploration:

1. **Concept → Role Discovery**
   ```bash
   ep probe -t AAPL --concept ".*[Aa]ssets.*"
   # Shows roles containing asset concepts
   ```

2. **Role → Concept Exploration**
   ```bash
   ep probe -t AAPL --role "StatementOfIncome"
   # Shows all concepts in that role, categorized
   ```

3. **Temporal Role Analysis**
   ```bash
   ep probe -t AAPL --role "StatementOfIncome" --timeline
   # Shows how role concepts evolved over time
   ```

### **Complete Workflow**
```bash
# 1. Discovery
ep probe -t AAPL --concept balance=".*Assets.*" income=".*Revenue.*"

# 2. Role Mapping (with temporal ranges - future feature)
ep new AAPL --balance StatementOfFinancialPositionClassified \
               --income StatementOfIncome \
               --cash StatementOfCashFlows

# 3. Data Extraction
ep update -t AAPL

# 4. Analysis
ep report -t AAPL --cat balance
```

## DATABASE DESIGN

### **Core Tables**
- **entities**: CIK (primary), ticker, name
- **filings**: SEC filing metadata with XBRL URLs
- **filing_roles**: Many-to-many company↔role mapping with labels
- **facts**: Extracted XBRL facts with context and dimensions
- **contexts**: Period information (instant, quarter, year modes)
- **concepts**: Company-specific concept definitions

### **Key Design Decisions**
- **Temporal coherence**: CIK-based lookups (immutable) vs ticker (can change)
- **Role flexibility**: Same user defined label, e.g. "balance", can map to multiple roles over time / filings / companies.
- **Fact deduplication**: Only store "best" fact per concept/period/dimension
- **Period derivation**: Smart quarter calculation from available data

## TECHNICAL IMPLEMENTATION NOTES

### **Dependencies**
- **Core**: sqlite3, pandas, tabulate, requests, arelle
- **Output**: colorama (for cross-platform terminal colors)
- **Standard library first**: Avoid dependencies unless clear value

## PROJECT PHILOSOPHY

### **Build for Yourself First**
- Personal productivity tool that saves real time
- No external pressure or artificial deadlines
- Quality over features - get the foundation right

### **Open Source Potential**
- Clean architecture suitable for collaboration
- Comprehensive documentation for contributors
- Permissive licensing for wide adoption
- "Soft promotion" strategy - let quality speak for itself

### **Long-term Vision**
- Transform from hobby project to widely-used financial analysis toolkit
- Enable sophisticated financial research through simple commands
- Bridge gap between financial domain expertise and technical implementation

---

*This document captures the foundational design principles and architectural decisions that guide the EDGAR CLI project. It should be updated only when core philosophy or major architectural patterns change.*