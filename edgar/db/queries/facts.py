"""
db.queries.facts - Fact query and insertion functions

Facts are the core financial data extracted from XBRL filings.
Each fact represents a specific value for a concept in a particular context.
"""
import sqlite3
from typing import Any, Optional

from edgar import db
from edgar.result import Result, ok, err, is_ok, is_not_ok


def _insert_context(conn: sqlite3.Connection, start_date: str, end_date: str, mode: str) -> Result[int, str]:
    """
    Insert context if missing and return xid (idempotent).

    A context represents a time period for a fact (instant, quarter, year, etc).
    """
    context_data = [{"start_date": start_date, "end_date": end_date, "mode": mode}]
    result = db.store.insert_or_ignore(conn, "contexts", context_data)
    if is_not_ok(result):
        return result

    query = "SELECT xid FROM contexts WHERE start_date = ? AND end_date = ? AND mode = ?"
    result = db.store.select(conn, query, (start_date, end_date, mode))
    if is_not_ok(result):
        return result

    contexts = result[1]
    if contexts:
        return ok(contexts[0]["xid"])
    else:
        return err(f"_insert_context({start_date}, {end_date}, {mode}): context not found after insert")


def _insert_unit(conn: sqlite3.Connection, unit_name: str) -> Result[int, str]:
    """
    Insert unit if missing and return unid (idempotent).

    A unit represents the measurement unit for a fact (USD, shares, etc).
    """
    unit_data = [{"name": unit_name}]
    result = db.store.insert_or_ignore(conn, "units", unit_data)
    if is_not_ok(result):
        return result

    query = "SELECT unid FROM units WHERE name = ?"
    result = db.store.select(conn, query, (unit_name,))
    if is_not_ok(result):
        return result

    units = result[1]
    if units:
        return ok(units[0]["unid"])
    else:
        return err(f"_insert_unit({unit_name}): unit not found after insert")


def select_past_modes(conn: sqlite3.Connection, cik: str, fiscal_year: str, cid: int, dimensions: dict[str, str]) -> Result[list[dict[str, Any]], str]:
    """
    Get existing fact modes for a concept to help quarterly selection.
    Returns: [{"mode": "quarter", "fiscal_period": "Q1"}, ...]

    IMPORTANT: Matches by concept TAG (not CID) because the same concept
    may have different CIDs across years due to taxonomy version changes
    (e.g., us-gaap/2023 vs us-gaap/2024).

    This finds facts matching: cik, fiscal_year, concept_tag
    If dimensions provided, match those too.
    Join with contexts to get mode, join with dei to get fiscal_period.
    """
    # First, get the tag for this CID
    query_tag = "SELECT tag FROM concepts WHERE cid = ?"
    result = db.store.select(conn, query_tag, (cid,))
    if is_not_ok(result) or not result[1]:
        return err(f"select_past_modes: concept {cid} not found")

    tag = result[1][0]["tag"]

    if dimensions:
        # Complex query with dimension matching - match by TAG instead of CID
        # For each fact, check if it has ALL the dimensions with matching members
        query = """
            SELECT DISTINCT ctx.mode, d.fiscal_period
            FROM facts f
            JOIN concepts c ON f.cid = c.cid
            JOIN roles fr ON f.rid = fr.rid
            JOIN filings fil ON fr.access_no = fil.access_no
            JOIN dei d ON fr.access_no = d.access_no
            JOIN contexts ctx ON f.xid = ctx.xid
            WHERE fil.cik = ?
            AND d.fiscal_year = ?
            AND c.tag = ?
            AND (
                SELECT COUNT(*) FROM dimensions dim
                WHERE dim.fid = f.fid
            ) = ?
        """
        params = [cik, fiscal_year, tag, len(dimensions)]

        # Add dimension match conditions
        for dim_name, dim_member in dimensions.items():
            query += """
                AND EXISTS (
                    SELECT 1 FROM dimensions dim
                    WHERE dim.fid = f.fid
                    AND dim.dimension = ?
                    AND dim.member = ?
                )
            """
            params.extend([dim_name, dim_member])

        return db.store.select(conn, query, tuple(params))
    else:
        # Simple query for consolidated facts - match by TAG instead of CID
        query = """
            SELECT DISTINCT ctx.mode, d.fiscal_period
            FROM facts f
            JOIN concepts c ON f.cid = c.cid
            JOIN roles fr ON f.rid = fr.rid
            JOIN filings fil ON fr.access_no = fil.access_no
            JOIN dei d ON fr.access_no = d.access_no
            JOIN contexts ctx ON f.xid = ctx.xid
            WHERE fil.cik = ?
            AND d.fiscal_year = ?
            AND c.tag = ?
            AND NOT EXISTS (
                SELECT 1 FROM dimensions dim
                WHERE dim.fid = f.fid
            )
        """
        return db.store.select(conn, query, (cik, fiscal_year, tag))


def insert(conn: sqlite3.Connection, facts_list: list[dict[str, Any]]) -> Result[int, str]:
    """
    Bulk insert facts with their dimensions and contexts.
    Returns count of facts inserted.

    For each fact record:
      1. Insert/get context (start_date, end_date, mode) -> xid
      2. Insert/get unit (unit name) -> unid
      3. Get rid from roles (access_no + role)
      4. Insert fact (rid, cid, xid, unid, value) -> fid
      5. If dimensions exist, insert into dimensions table

    fact record contains:
      - access_no
      - role
      - cid
      - value
      - start_date, end_date, mode
      - unit
      - dimensions (dict of {dim: member})
      - has_dimensions (bool)
    """
    if not facts_list:
        return ok(0)

    inserted_count = 0

    for fact in facts_list:
        try:
            # 1. Get or create context
            result = _insert_context(conn, str(fact["start_date"]), str(fact["end_date"]), fact["mode"])
            if is_not_ok(result):
                continue  # Skip this fact
            xid = result[1]

            # 2. Get or create unit
            if fact.get("unit"):
                result = _insert_unit(conn, fact["unit"])
                if is_not_ok(result):
                    continue
                unid = result[1]
            else:
                # No unit - skip this fact
                continue

            # 3. Get rid from roles
            result = db.queries.roles.insert_or_ignore(conn, fact["access_no"], fact["role"])
            if is_not_ok(result):
                continue
            rid = result[1]

            # 4. Insert fact
            fact_data = [{
                "rid": rid,
                "cid": fact["cid"],
                "xid": xid,
                "unid": unid,
                "value": fact["value"],
                "decimals": fact.get("decimals")
            }]

            result = db.store.insert_or_ignore(conn, "facts", fact_data)
            if is_not_ok(result):
                continue

            # Get the fid of the inserted/existing fact
            query = "SELECT fid FROM facts WHERE rid = ? AND cid = ? AND xid = ? AND unid = ?"
            result = db.store.select(conn, query, (rid, fact["cid"], xid, unid))
            if is_not_ok(result) or not result[1]:
                continue

            fid = result[1][0]["fid"]
            inserted_count += 1

            # 5. Insert dimensions if present
            if fact.get("has_dimensions") and fact.get("dimensions"):
                dim_records = [
                    {"fid": fid, "dimension": dim_name, "member": dim_member}
                    for dim_name, dim_member in fact["dimensions"].items()
                ]
                db.store.insert_or_ignore(conn, "dimensions", dim_records)

        except Exception:
            # Skip this fact and continue with others
            continue

    return ok(inserted_count)
