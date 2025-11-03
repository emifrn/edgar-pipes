# db module

## Purpose

The database module provides structured storage and retrieval for XBRL
financial data extracted from SEC filings.

## Architecture

The module is split into two layers. The db.store with the schema definition
and generic CRUD operations. The db.queries provide the business logic
interface, built on top of the db.store primitives. Ideally, all queries to the
database should pass through a db.queries function.

**`db.store`** - Low-level operations
- Schema definition
- Generic CRUD operations (select, insert, delete)
- Returns Result types for consistent error handling

**`db.queries`** - Domain-specific operations
- Organized by business domain (entities, filings, concepts, facts, etc.)
- Higher-level operations with business logic
- Built on top of db.store primitives

## Query naming conventions

Functions follow consistent patterns to make the API predictable:

- `get()` - single record by primary/unique key
- `get_id()` - lookup database ID by natural key
- `get_FIELD()` - retrieve specific field only
- `get_with_X()` - record enriched with JOIN data
- `select_*()` - multiple records with filtering
- `insert*()` - create records (usually idempotent)
- `update_*()` - modify existing records

## Module organization

```
db/
├── store.py          - Schema + low-level CRUD
└── queries/          - Domain-specific operations
    ├── entities.py   - Companies
    ├── filings.py    - SEC filings + metadata
    ├── concepts.py   - XBRL taxonomy concepts
    ├── roles.py      - XBRL presentation roles
    ├── facts.py      - Financial data + contexts/units
    ├── groups.py     - Pattern collections
    └── *_patterns.py - Regex patterns for extraction
```
