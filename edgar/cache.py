import re
import sys
import sqlite3
from typing import Any
from datetime import datetime

# Local modules

from edgar import db
from edgar import xbrl
from edgar.result import Result, ok, err, is_ok, is_not_ok


def resolve_entities(conn: sqlite3.Connection, tickers: list[str] | None) -> Result[list[dict[str, Any]], str]:
    """
    Return entities from cache or fetch from SEC API if missing.
    If tickers is None or empty: return all entities from DB (no network).
    Else: look up in DB; for any missing tickers, fetch from SEC and cache.
    """

    if not tickers:
        return db.queries.entity_select(conn, None)

    tickers = [t.lower() for t in tickers]
    
    # Get cached entities
    result = db.queries.entity_select(conn, tickers)
    if is_not_ok(result):
        return result
    
    found = result[1]
    have = {row["ticker"] for row in found}
    missing = [t for t in tickers if t not in have]

    if missing:
        # Fetch missing entities from SEC API
        result = xbrl.sec_api.entity_fetch_by_tickers(missing)
        if is_not_ok(result):
            return result
        
        entities = result[1]
        
        # Cache each entity
        for entity in entities:
            result = db.queries.entity_insert(conn, entity["cik"], entity["ticker"], entity["name"])
            if is_not_ok(result):
                return result
        
        # Get updated list including newly cached entities
        result = db.queries.entity_select(conn, tickers)
        if is_not_ok(result):
            return result
        
        found = result[1]

    return ok(found)


def filing_resolve_recent(conn: sqlite3.Connection, cik: str, form_types: set[str], after_date: datetime | None = None, force: bool = False) -> Result[list[dict[str, Any]], str]:
    """
    Return recent filings for a CIK, fetch and cache if missing.
    Respects after_date filter for both cached and fresh data.
    """
    
    after_str = after_date.strftime('%Y-%m-%d') if after_date else None

    if not force:
        # Check for cached filings with appropriate filter

        if after_date:
            date_filters = [('filing_date', '>=', after_str)]
            result = db.queries.entity_filings_select(conn, ciks=[cik], form_types=list(form_types), date_filters=date_filters)
        else:
            result = db.queries.entity_filings_select(conn, ciks=[cik], form_types=list(form_types))

        if is_not_ok(result):
            return result
    
        filings = result[1]
        
        # If we have cached filings that match our criteria, return them
        if filings:
            return ok(filings)
    
    # No suitable cached filings, fetch from SEC API
    result = xbrl.sec_api.filing_fetch_by_cik(cik, form_types)
    if is_not_ok(result):
        return result
    
    all_filings = result[1]
    if after_str:
        filtered_filings = [f for f in all_filings if f["filing_date"] >= after_str]
    else:
        filtered_filings = all_filings

    if filtered_filings:
        # Cache the filtered filings
        result = db.store.insert_or_ignore(conn, "filings", filtered_filings)
        if is_not_ok(result):
            return result
        
        # Return what we just cached
        return ok(filtered_filings)
    
    # No filings found matching criteria
    return ok([])


def resolve_xbrl_url(conn: sqlite3.Connection, cik: str, access_no: str) -> Result[str | None, str]:
    """
    Return cached XBRL file URL, fetch and cache if missing.
    Returns None if no XBRL file exists for this filing.
    """
    
    # Check if URL is already cached
    result = db.queries.filing_get_xbrl_url(conn, access_no)
    if is_not_ok(result):
        return result
    
    url = result[1]
    if url:
        return ok(url)
    
    # Not cached, fetch from SEC API
    result = xbrl.sec_api.filing_fetch_xbrl_url(cik, access_no)
    if is_not_ok(result):
        return result
    
    url = result[1]
    if url:
        # Cache the URL
        result = db.queries.filing_update_xbrl_url(conn, access_no, url)
        if is_not_ok(result):
            return result
        return ok(url)
    
    # No XBRL file exists for this filing
    return ok(None)


def filing_roles_resolve(conn: sqlite3.Connection, cik: str, access_no: str) -> Result[list[str], str]:
    """
    Get role names for a filing, fetching from XBRL if not cached.
    Returns list of unique role names.
    """

    result = db.queries.filing_roles_select(conn, access_no)
    if is_not_ok(result):
        return result

    roles = result[1]
    if roles:
        return ok(roles)

    result = resolve_xbrl_url(conn, cik, access_no)
    if is_not_ok(result):
        return result
    
    xbrl_url = result[1]
    if not xbrl_url:
        return err(f"cache.filing_roles_resolve: no XBRL file found for {access_no}")
    
    result = xbrl.arelle.load_model(xbrl_url)
    if is_not_ok(result):
        return result
    
    model = result[1]
    roles = xbrl.arelle.roles(model)
    if not roles:
        return ok([])
    
    cached = []
    for role in set(roles):
        result = db.queries.filing_roles_insert_or_ignore(conn, access_no, role)
        if is_ok(result):
            cached.append(role)

    return ok(cached)


def filing_role_concepts_resolve(conn: sqlite3.Connection, cik: str, access_no: str, role_name: str) -> Result[list[dict[str, Any]], str]:
    """
    Get concepts for a filing-role combination, fetching from XBRL if not cached.
    Returns list of concept records with taxonomy, tag, name.
    """
    
    result = db.queries.filing_role_concepts_select(conn, access_no, role_name)
    if is_not_ok(result):
        return result
    
    concepts = result[1]
    if concepts:
        return ok(concepts)
    
    result = resolve_xbrl_url(conn, cik, access_no)
    if is_not_ok(result):
        return result
    
    xbrl_url = result[1]
    if not xbrl_url:
        return err(f"filing_role_concepts_resolve: no XBRL file found for {access_no}")
    
    result = xbrl.arelle.load_model(xbrl_url)
    if is_not_ok(result):
        return result
    
    model = result[1]
    role_concepts = xbrl.arelle.role_concepts(model, role_name)
    if not role_concepts:
        return ok([])  # No concepts found for this role
    
    # Cache the concepts
    cached_concepts = []
    for concept in role_concepts:
        result = db.queries.concept_insert_or_ignore(conn, cik, concept["taxonomy"], concept["tag"], concept["name"])
        if is_not_ok(result):
            continue  # Skip this concept, continue with others
        
        concept_id = result[1]
        
        # Get role_id
        result = db.queries.filing_roles_insert_or_ignore(conn, access_no, role_name)
        if is_not_ok(result):
            continue
        
        role_id = result[1]
        
        # Link concept to role (insert into filing_role_concepts)
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO filing_role_concepts (rid, cid) VALUES (?, ?)", (role_id, concept_id))
            conn.commit()
            cursor.close()
        except sqlite3.Error:
            continue  # Skip this link, continue with others

        # Build concept record for return
        cached_concepts.append({
            "cid": concept_id,
            "cik": cik,
            "taxonomy": concept["taxonomy"],
            "tag": concept["tag"], 
            "name": concept["name"]
        })
    
    return ok(cached_concepts)
