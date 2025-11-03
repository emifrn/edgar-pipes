# Cache component

The cache component implements a smart resolution layer that sits between CLI
commands and data sources (database and SEC API). It provides fetch-on-demand
semantics: check the database first, fetch from the network if needed, cache
the result, and return it.

## Module overview

### cache.py - Resolution layer

Provides unified interface for resolving entities, filings, and XBRL metadata
with automatic caching.

Core functions:

- `resolve_entities(conn, user_agent, tickers)`: Resolve company entities by ticker
- `resolve_filings(conn, user_agent, cik, form_types, ...)`: Resolve recent filings
- `resolve_xbrl_url(conn, user_agent, cik, access_no)`: Resolve XBRL file URL
- `resolve_roles(conn, user_agent, cik, access_no)`: Resolve XBRL roles
- `resolve_concepts(conn, user_agent, cik, access_no, role_name)`: Resolve concepts

All functions follow the same pattern:

1. Check database for cached data
2. If found, return immediately
3. If not found, fetch from SEC API or XBRL file
4. Cache the fetched data in database
5. Return the data

Key implementation details:

Resolution chain: The `resolve_roles()` and `resolve_concepts()` functions
build on `resolve_xbrl_url()`, creating a dependency chain: first ensure the
XBRL URL is cached, then use it to load the XBRL model and extract metadata.

Partial updates: The `resolve_entities()` function only fetches missing
tickers from the SEC API, not the entire set. This minimizes network requests
when some entities are already cached.

Force refresh: The `resolve_filings()` function supports a `force` parameter
to bypass cache and fetch fresh data from the SEC API. This is useful when
users want to ensure they have the latest filings.

Date filtering: The `resolve_filings()` function applies `after_date` filtering
to both cached and fetched data, ensuring consistent behavior regardless of the
data source.

## Error handling

All functions return `Result[T, str]` types. Network failures, missing data,
and database errors are handled gracefully:

- `resolve_entities()`: Returns empty list if no entities found
- `resolve_filings()`: Returns empty list if no filings match criteria
- `resolve_xbrl_url()`: Returns `ok(None)` if no XBRL file exists
- `resolve_roles()`: Returns error if XBRL file missing, empty list if no roles
- `resolve_concepts()`: Returns error if XBRL file missing, empty list if no concepts

## Dependencies

External: sqlite3, datetime

Internal: edgar.db (database queries), edgar.xbrl (SEC API and XBRL parsing),
edgar.result (Result types)

## Usage pattern

The cache module is primarily used by CLI commands that need to discover and
fetch data from the SEC:

```python
from edgar import cache

# In a CLI command
result = cache.resolve_entities(conn, ["AAPL", "MSFT"], user_agent)
if is_ok(result):
    entities = result[1]
    for entity in entities:
        # Work with entity data
```

The probe command extensively uses cache resolution to populate the database
with entities, filings, roles, and concepts for later analysis.
