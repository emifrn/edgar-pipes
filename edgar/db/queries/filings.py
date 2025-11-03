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
                     group_filter: Optional[set[str]] = None) -> Result[list[dict[str, Any]], str]:
    """
    Select filings with flexible filtering options.

    Args:
        ciks: List of CIKs to filter by (None = all companies)
        access_nos: List of specific accession numbers to include
        form_types: List of form types to filter by (e.g., ['10-K', '10-Q'])
        date_filters: List of (field, operator, value) tuples for date filtering
                     e.g., [('filing_date', '>', '2024-01-01')]
        stubs_only: If True, only return filings without extracted facts
        group_filter: If provided with stubs_only=True, only return filings missing facts
                     for this specific set of groups (checks role+concept combinations)
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

    # Add stubs filter if requested
    if stubs_only and not group_filter:
        # Original behavior: return filings with no facts at all
        # Only use this when no group filter is specified
        where_clauses.append("""NOT EXISTS (
            SELECT 1 FROM facts
            JOIN roles ON facts.rid = roles.rid
            WHERE roles.access_no = f.access_no
        )""")

    # Construct final query
    if where_clauses:
        query = base_query + " WHERE " + " AND ".join(where_clauses)
    else:
        query = base_query

    query += " ORDER BY f.filing_date DESC"

    # Execute the base query first
    result = db.store.select(conn, query, tuple(params))
    if is_not_ok(result):
        return result

    filings = result[1]

    # If group_filter is specified with stubs_only, do post-processing to filter filings
    # that are missing facts for the specified groups
    if stubs_only and group_filter:
        filings = _filter_filings_missing_group_facts(conn, filings, group_filter)

    return ok(filings)


def _filter_filings_missing_group_facts(conn: sqlite3.Connection, filings: list[dict[str, Any]], group_filter: set[str]) -> list[dict[str, Any]]:
    """
    Filter filings to only those missing facts for specified groups.

    For each filing, check if it's missing facts for ANY of the groups in group_filter.
    A filing is "missing facts" for a group if:
    1. The filing has roles matching the group's role patterns, AND
    2. The group has concept patterns defined, AND
    3. Facts don't exist for ALL role+concept combinations

    This uses application-level regex matching which is more portable than SQL REGEXP.
    """
    if not filings or not group_filter:
        return filings

    filtered = []

    for filing in filings:
        access_no = filing["access_no"]
        cik = filing["cik"]

        # Check if this filing is missing facts for ANY of the specified groups
        missing_for_any_group = False

        for group_name in group_filter:
            # Get the group ID
            result = db.queries.groups.get_id(conn, group_name)
            if is_not_ok(result) or result[1] is None:
                continue  # Group doesn't exist, skip

            gid = result[1]

            # Get role patterns for this group
            result = db.queries.role_patterns.select_by_group(conn, gid, cik)
            if is_not_ok(result):
                continue

            role_patterns = result[1]
            if not role_patterns:
                continue  # No role patterns for this group

            # Get concept patterns for this group
            result = db.queries.concept_patterns.select_by_group(conn, gid, cik)
            if is_not_ok(result):
                continue

            concept_patterns = result[1]
            if not concept_patterns:
                continue  # No concept patterns for this group

            # Get roles for this filing
            result = db.queries.roles.select_by_filing(conn, access_no)
            if is_not_ok(result):
                continue

            filing_roles = result[1]
            if not filing_roles:
                continue  # No roles in this filing

            # Match filing roles against role patterns
            matched_roles = []
            for role_pattern in role_patterns:
                try:
                    regex = re.compile(role_pattern["pattern"])
                    for role_name in filing_roles:
                        if regex.search(role_name):
                            matched_roles.append(role_name)
                except re.error:
                    continue  # Skip invalid pattern

            if not matched_roles:
                continue  # This filing has no roles matching this group's patterns

            # Now check if facts exist for all matched_role x concept_pattern combinations
            # Get concepts that match the concept patterns
            result = db.queries.concepts.select_by_entity(conn, cik)
            if is_not_ok(result):
                continue

            all_concepts = result[1]

            # Match concepts against concept patterns
            matched_concepts = []
            for concept_pattern in concept_patterns:
                try:
                    regex = re.compile(concept_pattern["pattern"])
                    for concept in all_concepts:
                        if regex.search(concept["tag"]):
                            matched_concepts.append(concept)
                except re.error:
                    continue

            if not matched_concepts:
                # No matching concepts found - this is suspicious but not necessarily an error
                # Consider it as "missing facts" since we can't extract anything
                missing_for_any_group = True
                break

            # Check if facts exist for ALL matched_role x matched_concept combinations
            # We need at least ONE fact per concept pattern (across all matched roles)
            concepts_with_facts = set()

            for concept in matched_concepts:
                cid = concept["cid"]

                # Check if a fact exists for this concept in any of the matched roles
                query = """
                    SELECT 1
                    FROM facts f
                    JOIN roles fr ON f.rid = fr.rid
                    WHERE fr.access_no = ?
                    AND f.cid = ?
                    LIMIT 1
                """
                result = db.store.select(conn, query, (access_no, cid))
                if is_ok(result) and result[1]:
                    # Found a fact for this concept
                    concepts_with_facts.add(cid)

            # If we don't have facts for ALL matched concepts, this filing is missing facts for this group
            matched_concept_ids = {c["cid"] for c in matched_concepts}
            if concepts_with_facts != matched_concept_ids:
                missing_for_any_group = True
                break

        if missing_for_any_group:
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
