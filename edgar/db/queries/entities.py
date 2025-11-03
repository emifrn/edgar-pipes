import sqlite3
from typing import Any, Optional

from edgar import db
from edgar.result import Result, ok, err, is_ok


def get(conn: sqlite3.Connection,
        cik: Optional[str] = None,
        ticker: Optional[str] = None) -> Result[Optional[dict[str, Any]], str]:
    """
    Get entity by cik or ticker. Exactly one must be provided.
    Returns None if entity not found.
    """
    if cik is not None and ticker is not None:
        return err("entities.get: provide either cik or ticker, not both")

    if cik is not None:
        query = "SELECT cik, ticker, name FROM entities WHERE cik = ?"
        params = (cik,)
    elif ticker is not None:
        query = "SELECT cik, ticker, name FROM entities WHERE ticker = ?"
        params = (ticker.lower(),)
    else:
        return err("entities.get: must provide either cik or ticker")

    result = db.store.select(conn, query, params)
    if is_ok(result):
        entities = result[1]
        return ok(entities[0] if entities else None)
    return result


def select(conn: sqlite3.Connection, tickers: Optional[list[str]] = None) -> Result[list[dict[str, Any]], str]:
    """
    Get all entities, optionally filtered by ticker list.
    """
    if tickers:
        placeholders = ",".join("?" for _ in tickers)
        query = f"SELECT cik, ticker, name FROM entities WHERE ticker IN ({placeholders}) ORDER BY ticker"
        return db.store.select(conn, query, tuple(t.lower() for t in tickers))
    else:
        return db.store.select(conn, "SELECT cik, ticker, name FROM entities ORDER BY ticker")
