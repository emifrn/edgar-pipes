# XBRL component

The XBRL component wraps the Arelle library for parsing XBRL instance documents
and provides utilities for fetching filing data from the SEC EDGAR API. Three
modules handle different aspects of XBRL processing.

## Module overview

### arelle.py - Arelle wrapper

Wraps the Arelle library to extract structured data from XBRL instance documents.

Core functions:

- `load_model(file_url)`: Downloads and parses XBRL document, returns ModelXbrl
- `extract_roles(model)`: Extracts role URI tails from presentation linkbase
- `extract_facts_by_role(model, role_tail)`: Traverses presentation hierarchy to collect facts
- `extract_concepts_by_role(model, role)`: Deduplicates concepts from role facts
- `extract_dei(model, access_no)`: Pulls Document Entity Information with date normalization

Key implementation details:

Role URI handling: The code stores only the URI tail (last path segment) for
brevity. Full URIs are reconstructed by matching tails against `model.roleTypes`
with case-insensitive matching to handle variations.

Presentation traversal: `extract_facts_by_role()` walks the parent-child arcrole
relationships using depth-first search with cycle detection. The relationship
set filters by presentation linkrole. Facts are collected via
`model.factsByQname` using concept qnames found in the presentation tree.

DEI extraction: Handles malformed fiscal dates gracefully. If one fiscal date
(start or end) is missing, calculates it from the other using timedelta.
Various date formats are normalized to MM-DD.

### sec_api.py - SEC EDGAR API client

Fetches filing metadata and locates XBRL files from SEC public endpoints.

Core functions:

- `fetch_entities_by_tickers(user_agent, tickers)`: Fetch company info from company_tickers.json
- `fetch_filings_by_cik(user_agent, cik, form_types)`: Fetch filings from submissions endpoint
- `fetch_filing_xbrl_url(user_agent, cik, accno)`: Locate XBRL file in filing directory

XBRL file detection: The `fetch_filing_xbrl_url()` function first fetches the
filing's index.json to list available files. It prefers .xml files over
.htm/.html, then checks each file's content for XBRL markers (`<xbrl` or `<ix:`)
using the `net.check_content()` utility. This avoids false positives from
filename extensions alone.

CIK formatting: The entity fetch zero-pads CIK to 10 digits using
`f"{int(entity['cik_str']):010d}"` to match database format.

Session management: Uses requests.Session with retry logic (3 retries,
exponential backoff) for resilience against transient network failures.

### facts.py - Fact extraction utilities

Converts Arelle fact objects to database record format and classifies reporting
periods.

Core functions:

- `make_record(fact, access_no, role, concept_id)`: Convert fact to database record
- `get_concept(fact)`: Extract taxonomy URI and tag from fact qname
- `taxonomy_name(taxonomy_uri)`: Parse taxonomy name with version from URI
- `is_consolidated(fact)`: Check if fact has no segments or dimensions
- `_mode_from_days(days)`: Classify period mode from duration

Period classification: The `_mode_from_days()` helper maps duration to period
type using tolerances: quarter (88-95 days), semester (170-185), threeQ
(260-275), year (350-373). Tolerances handle variations in actual reporting
periods (e.g., quarters aren't exactly 91 days).

Dimension handling: `make_record()` extracts dimensions from context.dims and
stores as dict. The `is_consolidated()` check ensures only entity-level facts
are processed (no segment/member breakdowns). Dimensional data support is
planned for future versions.

Best fact selection: The `get_best_q*()` and `get_best_fy()` functions
implement heuristics for selecting the most appropriate fact when multiple
candidates exist. For Q2, a semester fact is preferred if Q1 exists (enables
subtraction to isolate Q2). For Q3, a threeQ fact is preferred if prior
quarters exist. These functions support the update command's fact extraction
logic.

### net.py - HTTP utilities

Provides HTTP utilities for fetching data from SEC EDGAR API with retry logic.

Core functions:

- `fetch_json(user_agent, url)`: Fetch and parse JSON from URL
- `fetch_text(user_agent, url)`: Fetch raw text content from URL
- `check_content(user_agent, url, patterns)`: Check if URL contains any patterns

Implementation: Uses requests.Session with automatic retry logic (3 retries,
exponential backoff) for resilience against transient network failures. All
functions follow the Result type pattern for explicit error handling, returning
descriptive error messages for timeouts, connection failures, and HTTP errors.

## Error handling

All functions return `Result[T, str]` types. Network failures, missing XBRL
files, and malformed data are handled gracefully:

- `load_model()`: Captures Arelle exceptions and returns err with context
- `fetch_filing_xbrl_url()`: Returns `ok(None)` if no XBRL file found
- `extract_dei()`: Validates dates, pops invalid fields rather than failing
- `make_record()`: Returns empty dict for facts without valid context

## Dependencies

External: Arelle (XBRL parsing), requests (HTTP), urllib3 (retry logic)

Internal: edgar.result (Result types)

## Known limitations

- Only processes consolidated facts (dimensional data not yet supported)
- Period classification tolerances may not cover all edge cases
- No rate limiting for SEC API requests
