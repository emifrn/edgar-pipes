# ADR 002: Result types for error handling

The edgar-pipes database operations and external API calls can fail. Python's
default exception-based error handling makes it easy to miss error cases and
leads to unpredictable control flow.

## Decision

Use explicit Result[T, str] types for all fallible operations:

```python
Result = tuple[Literal[True], T] | tuple[Literal[False], str]

# Usage
result = db.queries.entities.get(conn, ticker="AAPL")
if is_ok(result):
    entity = result[1]
else:
    error_msg = result[1]
```

## Consequences

**Positive:**
- Errors are explicit in type signatures
- Impossible to ignore error cases (type checker enforces handling)
- Clear distinction between success and failure paths
- Errors propagate cleanly through pipelines

**Negative:**
- More verbose than exceptions
- Requires discipline to check results consistently
- Additional helper functions needed (is_ok, is_not_ok, ok, err)

## Notes

This decision aligns with functional programming principles and makes error
handling predictable.
