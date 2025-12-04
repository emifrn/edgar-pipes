import re
import sys
import sqlite3
from typing import Any

# Local modules

from edgar import db
from edgar import xbrl
from edgar.result import Result, ok, err, is_ok, is_not_ok


def resolve_entities(conn: sqlite3.Connection, user_agent: str, tickers: list[str] | None) -> Result[tuple[list[dict[str, Any]], str], str]:
    """
    Return entities from cache or fetch from SEC API if missing.
    If tickers is None or empty: return all entities from DB (no network).
    Else: look up in DB; for any missing tickers, fetch from SEC and cache.
    Returns tuple of (entities, source) where source is "db" or "sec".
    """

    if not tickers:
        result = db.queries.entities.select(conn, None)
        if is_not_ok(result):
            return result
        return ok((result[1], "db"))

    tickers = [t.lower() for t in tickers]

    # Get cached entities
    result = db.queries.entities.select(conn, tickers)
    if is_not_ok(result):
        return result

    found = result[1]
    have = {row["ticker"] for row in found}
    missing = [t for t in tickers if t not in have]

    if missing:
        # Fetch missing entities from SEC API
        result = xbrl.sec_api.fetch_entities_by_tickers(user_agent, missing)
        if is_not_ok(result):
            return result

        entities = result[1]

        # Cache each entity
        for entity in entities:
            data = [{"cik": entity["cik"], "ticker": entity["ticker"].lower(), "name": entity["name"]}]
            result = db.store.insert(conn, "entities", data)
            if is_not_ok(result):
                return result

        # Get updated list including newly cached entities
        result = db.queries.entities.select(conn, tickers)
        if is_not_ok(result):
            return result

        found = result[1]
        return ok((found, "sec"))

    return ok((found, "db"))


def resolve_filings(conn: sqlite3.Connection, user_agent: str, cik: str, form_types: set[str], date_filters: list[tuple[str, str, str]] | None = None, force: bool = False, sort_order: str = "ASC") -> Result[tuple[list[dict[str, Any]], str], str]:
    """
    Return recent filings for a CIK, fetch and cache if missing.
    Respects date_filters for both cached and fresh data.
    Returns tuple of (filings, source) where source is "db" or "sec".

    Args:
        sort_order: Sort order for filings ("ASC" or "DESC").
                   Default "ASC" for chronological data processing.
    """

    if not force:
        # Check for cached filings with appropriate filter
        result = db.queries.filings.select_by_entity(conn, ciks=[cik], form_types=list(form_types), date_filters=date_filters, sort_order=sort_order)

        if is_not_ok(result):
            return result

        filings = result[1]

        # If we have cached filings that match our criteria, return them
        if filings:
            return ok((filings, "db"))

    # No suitable cached filings, fetch from SEC API
    result = xbrl.sec_api.fetch_filings_by_cik(user_agent, cik, form_types)
    if is_not_ok(result):
        return result

    all_filings = result[1]

    # Apply date filters to fetched data
    filtered_filings = all_filings
    if date_filters:
        for field, operator, value in date_filters:
            if field == 'filing_date':
                if operator == '>':
                    filtered_filings = [f for f in filtered_filings if f["filing_date"] > value]
                elif operator == '>=':
                    filtered_filings = [f for f in filtered_filings if f["filing_date"] >= value]
                elif operator == '<':
                    filtered_filings = [f for f in filtered_filings if f["filing_date"] < value]
                elif operator == '<=':
                    filtered_filings = [f for f in filtered_filings if f["filing_date"] <= value]
                elif operator == '=':
                    filtered_filings = [f for f in filtered_filings if f["filing_date"] == value]
                elif operator in ('!=', '<>'):
                    filtered_filings = [f for f in filtered_filings if f["filing_date"] != value]

    if filtered_filings:
        # Sort filings according to sort_order (SEC API returns newest first)
        reverse = (sort_order == "DESC")
        filtered_filings = sorted(filtered_filings, key=lambda f: f.get("filing_date", ""), reverse=reverse)

        # Cache the filtered filings
        result = db.store.insert_or_ignore(conn, "filings", filtered_filings)
        if is_not_ok(result):
            return result

        # Return what we just cached
        return ok((filtered_filings, "sec"))

    # No filings found matching criteria
    return ok(([], "sec"))


def resolve_xbrl_url(conn: sqlite3.Connection, user_agent: str, cik: str, access_no: str) -> Result[str | None, str]:
    """
    Return cached XBRL file URL, fetch and cache if missing.
    Returns None if no XBRL file exists for this filing.
    """

    # Check if URL is already cached
    result = db.queries.filings.get_xbrl_url(conn, access_no)
    if is_not_ok(result):
        return result

    url = result[1]
    if url:
        return ok(url)

    # Not cached, fetch from SEC API
    result = xbrl.sec_api.fetch_filing_xbrl_url(user_agent, cik, access_no)
    if is_not_ok(result):
        return result
    
    url = result[1]
    if url:
        # Cache the URL
        result = db.queries.filings.update_xbrl_url(conn, access_no, url)
        if is_not_ok(result):
            return result
        return ok(url)
    
    # No XBRL file exists for this filing
    return ok(None)


def resolve_roles(conn: sqlite3.Connection, user_agent: str, cik: str, access_no: str) -> Result[tuple[list[str], str], str]:
    """
    Get role names for a filing, fetching from XBRL if not cached.
    Returns tuple of (role_names, source) where source is "db" or "sec".
    """

    result = db.queries.roles.select_by_filing(conn, access_no)
    if is_not_ok(result):
        return result

    roles = result[1]
    if roles:
        return ok((roles, "db"))

    result = resolve_xbrl_url(conn, user_agent, cik, access_no)
    if is_not_ok(result):
        return result

    xbrl_url = result[1]
    if not xbrl_url:
        return err(f"cache.resolve_roles: no XBRL file found for {access_no}")

    result = xbrl.arelle.load_model(xbrl_url)
    if is_not_ok(result):
        return result

    model = result[1]
    roles = xbrl.arelle.extract_roles(model)
    if not roles:
        return ok(([], "sec"))

    cached = []
    for role in set(roles):
        result = db.queries.roles.insert_or_ignore(conn, access_no, role)
        if is_ok(result):
            cached.append(role)

    return ok((cached, "sec"))


def resolve_concepts(conn: sqlite3.Connection, user_agent: str, cik: str, access_no: str, role_name: str) -> Result[tuple[list[dict[str, Any]], str], str]:
    """
    Get concepts for a filing-role combination, fetching from XBRL if not cached.
    Returns tuple of (concepts, source) where source is "db" or "sec".
    """

    result = db.queries.concepts.select_by_role(conn, access_no, role_name)
    if is_not_ok(result):
        return result

    concepts = result[1]
    if concepts:
        return ok((concepts, "db"))

    result = resolve_xbrl_url(conn, user_agent, cik, access_no)
    if is_not_ok(result):
        return result

    xbrl_url = result[1]
    if not xbrl_url:
        return err(f"cache.resolve_concepts: no XBRL file found for {access_no}")
    
    result = xbrl.arelle.load_model(xbrl_url)
    if is_not_ok(result):
        return result
    
    model = result[1]
    role_concepts = xbrl.arelle.extract_concepts_by_role(model, role_name)
    if not role_concepts:
        return ok(([], "sec"))  # No concepts found for this role
    
    # Cache the concepts
    cached_concepts = []
    for concept in role_concepts:
        # Insert concept if missing
        concept_data = [{
            "cik": cik,
            "taxonomy": concept["taxonomy"],
            "tag": concept["tag"],
            "name": concept["name"],
            "balance": concept.get("balance")  # Include balance attribute for Q4 derivation
        }]
        result = db.store.insert_or_ignore(conn, "concepts", concept_data)
        if is_not_ok(result):
            continue  # Skip this concept, continue with others

        # Get the concept_id
        result = db.queries.concepts.get_id(conn, cik, concept["taxonomy"], concept["tag"])
        if is_not_ok(result):
            continue
        concept_id = result[1]
        
        # Get role_id
        result = db.queries.roles.insert_or_ignore(conn, access_no, role_name)
        if is_not_ok(result):
            continue
        
        role_id = result[1]
        
        # Link concept to role (insert into role_concepts)
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO role_concepts (rid, cid) VALUES (?, ?)", (role_id, concept_id))
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

    return ok((cached_concepts, "sec"))
