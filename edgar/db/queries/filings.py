import re
import sqlite3
from typing import Any, Optional

from edgar import db
from edgar.result import Result, ok, err, is_ok, is_not_ok


# =============================================================================
# FILING QUERIES
# =============================================================================

def get_cik(conn: sqlite3.Connection, access_no: str) -> Result[Optional[str], str]:
    """
    Get CIK for a filing.
    """
    query = "SELECT cik FROM filings WHERE access_no = ?"
    result = db.store.select(conn, query, (access_no,))
    if is_ok(result):
        filings = result[1]
        return ok(filings[0]["cik"] if filings else None)
    else:
        return result


def get_xbrl_url(conn: sqlite3.Connection, access_no: str) -> Result[str | None, str]:
    """
    Get XBRL URL for a filing.
    """
    query = "SELECT xbrl_url FROM filings WHERE access_no = ?"
    result = db.store.select(conn, query, (access_no,))
    if is_ok(result):
        filings = result[1]
        if filings:
            return ok(filings[0]["xbrl_url"])
        else:
            return ok(None)  # Filing not found
    else:
        return result


def update_xbrl_url(conn: sqlite3.Connection, access_no: str, url: str) -> Result[int, str]:
    """
    Update XBRL URL for a filing.
    """
    try:
        query = "UPDATE filings SET xbrl_url = ? WHERE access_no = ?"
        cursor = conn.execute(query, (url, access_no))
        count = cursor.rowcount
        conn.commit()
        return ok(count)
    except sqlite3.Error as e:
        return err(f"queries.filings.update_xbrl_url({access_no}, ...) sqlite error: {e}")


def get_with_entity(conn: sqlite3.Connection, access_no: str) -> Result[Optional[dict[str, Any]], str]:
    """
    Get filing with entity info.
    """
    query = """
        SELECT  f.access_no,
                f.cik,
                f.form_type,
                f.filing_date,
                f.xbrl_url,
                f.is_xbrl,
                f.is_ixbrl,
                e.ticker,
                e.name
        FROM filings f
        JOIN entities e ON f.cik = e.cik
        WHERE f.access_no = ?
        """
    result = db.store.select(conn, query, (access_no,))
    if is_ok(result):
        filings = result[1]
        return ok(filings[0] if filings else None)
    else:
        return result


def select_by_entity(conn: sqlite3.Connection,
                     ciks: Optional[list[str]] = None,
                     access_nos: Optional[list[str]] = None,
                     form_types: Optional[list[str]] = None,
                     date_filters: Optional[list[tuple[str, str, str]]] = None,
                     stubs_only: bool = False,
                     group_filter: Optional[set[str]] = None,
                     sort_order: str = "DESC") -> Result[list[dict[str, Any]], str]:
    """
    Select filings with flexible filtering options.

    Args:
        ciks: List of CIKs to filter by (None = all companies)
        access_nos: List of specific accession numbers to include
        form_types: List of form types to filter by (e.g., ['10-K', '10-Q'])
        date_filters: List of (field, operator, value) tuples for date filtering
                     e.g., [('filing_date', '>', '2024-01-01')]
        stubs_only: If True, only return filings with no processed patterns (never processed)
        group_filter: If provided, only return filings that need processing for
                     this specific set of groups (checks processed patterns)
                     Note: group_filter takes precedence over stubs_only
        sort_order: Sort order for filings by filing_date ("ASC" or "DESC").
                   Default "DESC" (newest first) for display.
                   Use "ASC" (oldest first) for chronological data processing.
    """
    base_query = """
        SELECT  f.access_no,
                f.cik,
                f.form_type,
                f.primary_doc,
                f.filing_date,
                f.xbrl_url,
                f.is_xbrl,
                f.is_ixbrl,
                f.is_amendment,
                e.ticker,
                e.name
        FROM filings f
        JOIN entities e ON f.cik = e.cik
        """

    where_clauses = []
    params = []

    # Build WHERE clauses based on provided filters
    if ciks is not None and len(ciks) > 0:
        placeholders = ",".join("?" * len(ciks))
        where_clauses.append(f"f.cik IN ({placeholders})")
        params.extend(ciks)

    if access_nos is not None and len(access_nos) > 0:
        placeholders = ",".join("?" * len(access_nos))
        where_clauses.append(f"f.access_no IN ({placeholders})")
        params.extend(access_nos)

    if form_types is not None and len(form_types) > 0:
        placeholders = ",".join("?" * len(form_types))
        where_clauses.append(f"f.form_type IN ({placeholders})")
        params.extend(form_types)

    if date_filters is not None:
        for field, operator, value in date_filters:
            # Validate operator
            if operator not in ['>', '>=', '<', '<=', '=', '==', '!=', '<>']:
                return err(f"Invalid operator '{operator}' in date filter")

            # Normalize operators (== to =, etc.)
            if operator == '==':
                operator = '='
            elif operator == '!=':
                operator = '<>'

            # Validate field (for now just filing_date, but extensible)
            if field not in ['filing_date']:
                return err(f"Invalid date field '{field}' in date filter")

            where_clauses.append(f"f.{field} {operator} ?")
            params.append(value)

    # Add stubs filter if requested (only when no group_filter specified)
    if stubs_only and not group_filter:
        # Return filings with no processed patterns (never been processed)
        where_clauses.append("""NOT EXISTS (
            SELECT 1 FROM filing_patterns_processed
            WHERE access_no = f.access_no
        )""")

    # Construct final query
    if where_clauses:
        query = base_query + " WHERE " + " AND ".join(where_clauses)
    else:
        query = base_query

    # Validate and apply sort order
    if sort_order not in ["ASC", "DESC"]:
        return err(f"Invalid sort_order '{sort_order}'. Must be 'ASC' or 'DESC'.")
    query += f" ORDER BY f.filing_date {sort_order}"

    # Execute the base query first
    result = db.store.select(conn, query, tuple(params))
    if is_not_ok(result):
        return result

    filings = result[1]

    # If group_filter is specified, filter to filings needing processing for those groups
    if group_filter:
        filings = _filter_filings_missing_group_facts(conn, filings, group_filter)

    return ok(filings)


def _filter_filings_missing_group_facts(conn: sqlite3.Connection, filings: list[dict[str, Any]], group_filter: set[str]) -> list[dict[str, Any]]:
    """
    Filter filings to only those missing processed concept patterns for specified groups.

    A filing needs processing if ANY concept pattern for a group hasn't been probed yet.
    This is determined by checking the filing_patterns_processed table.
    """
    if not filings or not group_filter:
        return filings

    filtered = []

    for filing in filings:
        access_no = filing["access_no"]
        cik = filing["cik"]

        # Check if this filing is missing processed patterns for ANY of the specified groups
        needs_processing = False

        for group_name in group_filter:
            # Get the group ID
            result = db.queries.groups.get_id(conn, group_name)
            if is_not_ok(result) or result[1] is None:
                continue  # Group doesn't exist, skip

            gid = result[1]

            # Get concept patterns for this group
            result = db.queries.concept_patterns.select_by_group(conn, gid, cik)
            if is_not_ok(result):
                continue

            concept_patterns = result[1]
            if not concept_patterns:
                continue  # No concept patterns for this group

            # Check if all concept patterns have been processed for this filing
            pattern_ids = [p["pid"] for p in concept_patterns]

            if not pattern_ids:
                continue

            # Check if all patterns have been processed
            result = db.queries.filing_patterns_processed.is_fully_processed(conn, access_no, pattern_ids)
            if is_not_ok(result):
                continue

            fully_processed = result[1]

            # If not fully processed, this filing needs processing
            if not fully_processed:
                needs_processing = True
                break

        if needs_processing:
            filtered.append(filing)

    return filtered


def insert_dei(conn: sqlite3.Connection, data: dict[str, Any]) -> Result[int, str]:
    """
    Insert or update DEI (Document Entity Information) data for a filing (idempotent).

    Uses UPSERT to handle duplicate access_no - updates existing record if present.
    """
    try:
        query = """
            INSERT INTO dei (access_no, doc_type, doc_period_end, fiscal_year,
                           fiscal_month_day_start, fiscal_month_day_end, fiscal_period)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(access_no) DO UPDATE SET
                doc_type = excluded.doc_type,
                doc_period_end = excluded.doc_period_end,
                fiscal_year = excluded.fiscal_year,
                fiscal_month_day_start = excluded.fiscal_month_day_start,
                fiscal_month_day_end = excluded.fiscal_month_day_end,
                fiscal_period = excluded.fiscal_period
        """
        params = (
            data["access_no"],
            data.get("doc_type"),
            data.get("doc_period_end"),
            data.get("fiscal_year"),
            data.get("fiscal_month_day_start"),
            data.get("fiscal_month_day_end"),
            data.get("fiscal_period")
        )
        cursor = conn.execute(query, params)
        count = cursor.rowcount
        conn.commit()
        return ok(count)
    except sqlite3.Error as e:
        return err(f"queries.filings.insert_dei({data.get('access_no')}) sqlite error: {e}")
