# ADR 003: Pattern based fact extraction

## Context

XBRL filings vary significantly across companies. Apple uses
"StatementConsolidatedBalanceSheets" while Microsoft uses "BalanceSheet".
Hardcoding role/concept names for each company is unmaintainable.

## Decision

Use regex pattern matching with a two-level system:

1. **Role Patterns** - Identify which sections of filings contain relevant data
2. **Concept Patterns** - Identify which financial line items to extract

**Groups** bundle patterns into logical collections (e.g., "balance",
"income"), with many-to-many relationships allowing pattern reuse across
groups.

Patterns are company-specific (tied to CIK) since each company has unique XBRL
structure.

## Consequences

**Positive:**
- Handles variation in XBRL naming across companies
- Patterns are reusable and composable
- Users can refine extraction without code changes
- Supports both comprehensive and specialized views
- Adapts to temporal changes in company reporting

**Negative:**
- Requires user effort to define patterns
- Regex complexity can be challenging for users
- Pattern quality directly affects data quality
- Needs pattern discovery tools to guide users

## Notes

The pattern system transforms Edgar from a rigid extraction tool into a
flexible financial taxonomy management system. Groups enable sophisticated
analytical frameworks without code changes.
