# ADR 004: Fully Qualified Function Names

Edgar-pipes adopts a fully qualified naming policy where functions are always
called through their complete module path. This allows function names to be
simple and concise since the module hierarchy provides context.

**Simpler function names** - `get()` instead of `get_entity()` because
`db.queries.entities.get()` already provide entity context.

**Self-documenting code** - Reading `db.queries.facts.insert()` immediately
tells what module owns this operation.

**Eliminate naming conflicts** - Multiple modules can have `get()`, `select()`,
`insert()` without collision.

**Consistent style** - Every function call shows its complete lineage.

```python
# Import modules, not functions
from edgar import db

# Call with full qualification
result = db.queries.entities.get(conn, ticker="AAPL")
result = db.queries.filings.select_by_entity(conn, ciks=[cik])
result = db.queries.facts.insert(conn, facts_list)
```

## Exceptions

The `result` module acts more like a language extension than a typical module.
It provides fundamental primitives for error handling that are used throughout
the entire codebase, so brevity justifies breaking the rule.

```python
from edgar.result import Result, ok, err, is_ok, is_not_ok

# These are used so frequently that qualification would be noise
if is_ok(result):
    value = result[1]
else:
    error = result[1]
```
