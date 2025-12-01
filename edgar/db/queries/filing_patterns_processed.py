"""
Queries for filing_patterns_processed table.

This table tracks which concept patterns have been probed/processed for each filing,
enabling incremental builds to skip already-processed filings.

Available functions:
    count_processed(conn, access_no, pattern_ids) -> Result[int, str]
    is_fully_processed(conn, access_no, pattern_ids) -> Result[bool, str]
    insert(conn, access_no, pid) -> Result[int, str]
"""
import sqlite3
from typing import List

from edgar import db
from edgar.result import Result, ok, err, is_ok


def count_processed(conn: sqlite3.Connection, access_no: str, pattern_ids: List[int]) -> Result[int, str]:
    """
    Count how many of the given pattern IDs have been processed for a filing.

    Args:
        conn: Database connection
        access_no: Filing accession number
        pattern_ids: List of concept pattern IDs to check

    Returns:
        ok(count) - Number of patterns that have been processed
        err(msg) - Error message
    """
    if not pattern_ids:
        return ok(0)

    placeholders = ",".join("?" * len(pattern_ids))
    query = f"""
        SELECT COUNT(*)
        FROM filing_patterns_processed
        WHERE access_no = ?
        AND pid IN ({placeholders})
    """
    params = [access_no] + pattern_ids

    result = db.store.select(conn, query, tuple(params))
    if is_ok(result):
        count = result[1][0]["COUNT(*)"] if result[1] else 0
        return ok(count)
    else:
        return result


def is_fully_processed(conn: sqlite3.Connection, access_no: str, pattern_ids: List[int]) -> Result[bool, str]:
    """
    Check if all given pattern IDs have been processed for a filing.

    Args:
        conn: Database connection
        access_no: Filing accession number
        pattern_ids: List of concept pattern IDs to check

    Returns:
        ok(True) - All patterns have been processed
        ok(False) - Some patterns are missing
        err(msg) - Error message
    """
    result = count_processed(conn, access_no, pattern_ids)
    if is_ok(result):
        count = result[1]
        return ok(count == len(pattern_ids))
    else:
        return result


def insert(conn: sqlite3.Connection, access_no: str, pid: int) -> Result[int, str]:
    """
    Mark a concept pattern as processed for a filing.

    Uses INSERT OR IGNORE to handle duplicates gracefully.

    Args:
        conn: Database connection
        access_no: Filing accession number
        pid: Concept pattern ID

    Returns:
        ok(rowcount) - Number of rows inserted (0 if already exists)
        err(msg) - Error message
    """
    try:
        query = "INSERT OR IGNORE INTO filing_patterns_processed (access_no, pid) VALUES (?, ?)"
        cursor = conn.execute(query, (access_no, pid))
        count = cursor.rowcount
        conn.commit()
        return ok(count)
    except sqlite3.Error as e:
        return err(f"queries.filing_patterns_processed.insert({access_no}, {pid}) sqlite error: {e}")
