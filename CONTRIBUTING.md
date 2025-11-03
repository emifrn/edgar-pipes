# Contributing to edgar-pipes

This document outlines coding conventions and design patterns used in
edgar-pipes. Following these conventions ensures consistency and
maintainability across the codebase.

## Function Naming Conventions

Use consistent verbs that communicate both cost and behavior of
operations:

### Verb Guidelines

- **`get_`** = Cheap operations, generic lookups, returns one-or-None
- **`select_`** = Database-oriented operations, returns lists  
- **`fetch_`** = Expensive network operations
- **`load_`** = Expensive processing (parsing, transformation), may include network
- **`resolve_`** = Cache-backed operations, cheap if cached, expensive if cache miss
- **`make_`** = Build/construct something
- **`plurals`** = Indicates list returns (outside database context)

### Examples

```python
# Cheap database lookups
entity_get_by_cik()          # Returns single entity or None
filing_get(access_no)        # Returns single filing or None

# Database queries returning lists
entity_select()              # Returns list of entities
filing_select_recent()       # Returns list of filings

# Expensive network operations
filing_fetch_by_cik()        # SEC API call
entity_fetch_by_tickers()    # SEC API call

# Expensive processing
load_model(file_url)         # Parse XBRL document

# Cache-backed operations  
resolve_xbrl_url()           # Get URL from cache or fetch if missing

# Construction/building
make_record(fact, ...)       # Build database record

# List returns (non-DB context)
roles(xbrl)                  # Returns list of role names
```

## Import Strategy

### Fully Qualified Names (Default)

Use fully qualified imports for **all local modules** to maintain clarity and
avoid naming conflicts:

```python
import xbrl.facts
import db.store
import db.queries

# Usage
taxonomy, tag = xbrl.facts.get_concept(fact)
result = db.store.select(conn, query, params)
entity = db.queries.entity_get_by_cik(conn, cik)
```

### Exception: Result Module

The `result` module is treated as a **language extension** due to frequent
usage throughout the codebase and it is the only exception to fully qualified
imports

```python
from result import Result, ok, err, is_ok, is_not_ok, unwrap, unwrap_or

# Direct usage without qualification
def some_operation() -> Result[str, str]:
    if success:
        return ok("value")
    else:
        return err("error message")
```

## Design Patterns

### Result Pattern for Error Handling

- Use `Result[T, E]` for all operations that can fail
- Prefer explicit error handling over exceptions
- Chain operations using `is_ok()` and `is_not_ok()` checks
- Errors are propagated up to the main level for printing
