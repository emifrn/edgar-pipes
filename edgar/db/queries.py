import re
import sqlite3
from typing import Any, Optional

# Local modules
from edgar import db
from edgar.result import Result, ok, err, is_ok, is_not_ok


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def table_exists(conn: sqlite3.Connection, name: str) -> Result[bool, str]:
    """
    Return True if a table exists in the database.
    """
    try:
        query = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
        cursor = conn.execute(query, (name,))
        exists = cursor.fetchone() is not None
        return ok(exists)
    except sqlite3.Error as e:
        return err(f"queries.table_exists({name}) sqlite error: {e}")


# =============================================================================
# ENTITY OPERATIONS
# =============================================================================

def entity_insert(conn: sqlite3.Connection, cik: str, ticker: str, name: str) -> Result[int, str]:
    """
    Insert a new entity (assumes it doesn't exist).
    """
    data = [{"cik": cik, "ticker": ticker.lower(), "name": name}]
    return db.store.insert(conn, "entities", data)


def entity_insert_or_ignore(conn: sqlite3.Connection, cik: str, ticker: str, name: str) -> Result[int, str]:
    """
    Insert a new entity.
    """
    data = [{"cik": cik, "ticker": ticker.lower(), "name": name}]
    return db.store.insert_or_ignore(conn, "entities", data)


def entity_get_by_cik(conn: sqlite3.Connection, cik: str) -> Result[Optional[dict[str, Any]], str]:
    """
    Get entity by CIK.
    """
    query = "SELECT cik, ticker, name FROM entities WHERE cik = ?"
    result = db.store.select(conn, query, (cik,))
    if is_ok(result):
        entities = result[1]
        return ok(entities[0] if entities else None)
    else:
        return result


def entity_get_by_ticker(conn: sqlite3.Connection, ticker: str) -> Result[Optional[dict[str, Any]], str]:
    """
    Get entity by ticker symbol.
    """
    query = "SELECT cik, ticker, name FROM entities WHERE ticker = ?"
    result = db.store.select(conn, query, (ticker.lower(),))
    if is_ok(result):
        entities = result[1]
        return ok(entities[0] if entities else None)
    else:
        return result


def entity_select(conn: sqlite3.Connection, tickers: Optional[list[str]] = None) -> Result[list[dict[str, Any]], str]:
    """
    Get all entities, optionally filtered by ticker list.
    """
    if tickers:
        placeholders = ",".join("?" for _ in tickers)
        query = f"SELECT cik, ticker, name FROM entities WHERE ticker IN ({placeholders}) ORDER BY ticker"
        return db.store.select(conn, query, tuple(t.lower() for t in tickers))
    else:
        return db.store.select(conn, "SELECT cik, ticker, name FROM entities ORDER BY ticker")


def entity_select_concepts(conn: sqlite3.Connection, cik: str, taxonomy: Optional[str] = None) -> Result[list[dict[str, Any]], str]:
    """
    Get all concepts for an entity, optionally filtered by taxonomy.
    """
    if taxonomy:
        query = "SELECT cid, taxonomy, tag, name FROM concepts WHERE cik = ? AND taxonomy = ? ORDER BY tag"
        return db.store.select(conn, query, (cik, taxonomy))
    else:
        query = "SELECT cid, taxonomy, tag, name FROM concepts WHERE cik = ? ORDER BY taxonomy, tag"
        return db.store.select(conn, query, (cik,))


def entity_delete(conn: sqlite3.Connection, cik: str) -> Result[int, str]:
    """
    Delete entity and all related data (cascading).
    """
    return db.store.delete(conn, "entities", "cik", [cik])


# =============================================================================
# FILING OPERATIONS
# =============================================================================

def filing_get_cik(conn: sqlite3.Connection, access_no: str) -> Result[Optional[str], str]:
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


def filing_get_xbrl_url(conn: sqlite3.Connection, access_no: str) -> Result[str | None, str]:
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


def filing_update_xbrl_url(conn: sqlite3.Connection, access_no: str, url: str) -> Result[int, str]:
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
        return err(f"queries.filing_update_xbrl_url({access_no}, ...) sqlite error: {e}")


def filing_delete(conn: sqlite3.Connection, access_no: str) -> Result[int, str]:
    """
    Delete filing and all associated data (cascading).
    """
    return db.store.delete(conn, "filings", "access_no", [access_no])


# =============================================================================
# ENTITY - FILING OPERATIONS. Returns joined data
# =============================================================================


def entity_filing_get(conn: sqlite3.Connection, access_no: str) -> Result[Optional[dict[str, Any]], str]:
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


def entity_filings_select(conn: sqlite3.Connection,
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
            JOIN filing_roles ON facts.rid = filing_roles.rid
            WHERE filing_roles.access_no = f.access_no
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
            result = group_get_id(conn, group_name)
            if is_not_ok(result) or result[1] is None:
                continue  # Group doesn't exist, skip

            gid = result[1]

            # Get role patterns for this group
            result = role_pattern_select_by_group(conn, gid, cik)
            if is_not_ok(result):
                continue

            role_patterns = result[1]
            if not role_patterns:
                continue  # No role patterns for this group

            # Get concept patterns for this group
            result = concept_pattern_select_by_group(conn, gid, cik)
            if is_not_ok(result):
                continue

            concept_patterns = result[1]
            if not concept_patterns:
                continue  # No concept patterns for this group

            # Get roles for this filing
            result = filing_roles_select(conn, access_no)
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
            result = entity_select_concepts(conn, cik)
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
                    JOIN filing_roles fr ON f.rid = fr.rid
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


# =============================================================================
# ROLE OPERATIONS
# =============================================================================

def filing_roles_insert_or_ignore(conn: sqlite3.Connection, access_no: str, role_name: str) -> Result[int, str]:
    """
    Insert role for a filing if it doesn't exist, return rid.
    """
    # First try to insert
    data = [{"access_no": access_no, "name": role_name}]
    result = db.store.insert_or_ignore(conn, "filing_roles", data)
    if is_not_ok(result):
        return result
    
    # Get the rid (whether newly inserted or existing)
    query = "SELECT rid FROM filing_roles WHERE access_no = ? AND name = ?"
    result = db.store.select(conn, query, (access_no, role_name))
    if is_not_ok(result):
        return result
    
    if result[1]:
        return ok(result[1][0]["rid"])
    else:
        return err(f"filing_roles_insert_or_ignore: role not found after insert")


def filing_roles_select(conn: sqlite3.Connection, access_no: str) -> Result[list[str], str]:
    """
    Get role names for a filing.
    """
    query = "SELECT name FROM filing_roles WHERE access_no = ? ORDER BY name"
    result = db.store.select(conn, query, (access_no,))
    if is_ok(result):
        roles = result[1]
        return ok([role["name"] for role in roles])
    else:
        return result


def filing_roles_select_detailed(conn: sqlite3.Connection, 
                                 access_nos: list[str], 
                                 pattern: Optional[str] = None) -> Result[list[dict[str, Any]], str]:
    """
    Get detailed role information for specified filings with optional pattern filtering.
    Returns role records with full entity and filing context.
    """
    if not access_nos:
        return ok([])
    
    placeholders = ",".join("?" * len(access_nos))
    query = f"""
        SELECT  e.name,
                e.ticker, 
                e.cik,
                f.access_no,
                f.filing_date,
                f.form_type,
                fr.name as role_name
        FROM filing_roles fr
        JOIN filings f ON fr.access_no = f.access_no
        JOIN entities e ON f.cik = e.cik
        WHERE f.access_no IN ({placeholders})
        ORDER BY f.filing_date DESC, e.ticker, fr.name
        """
    
    result = db.store.select(conn, query, tuple(access_nos))
    if is_not_ok(result):
        return result
    
    roles = result[1]
    
    if pattern:
        try:
            rexp = re.compile(pattern)
            filtered_roles = [role for role in roles if rexp.search(role['role_name'])]
            return ok(filtered_roles)
        except re.error as e:
            return err(f"filing_roles_select_detailed: invalid regex pattern '{pattern}': {e}")
    
    return ok(roles)


def filing_roles_count(conn: sqlite3.Connection, access_no: str) -> Result[int, str]:
    """
    Get count of roles for a filing.
    """
    query = "SELECT COUNT(*) as count FROM filing_roles WHERE access_no = ?"
    result = db.store.select(conn, query, (access_no,))
    if is_ok(result):
        rows = result[1]
        return ok(rows[0]["count"] if rows else 0)
    else:
        return result


# =============================================================================
# CONCEPT OPERATIONS
# =============================================================================

def concept_get_id(conn: sqlite3.Connection, cik: str, taxonomy: str, tag: str) -> Result[Optional[int], str]:
    """
    Get cid for a specific concept.
    """
    query = "SELECT cid FROM concepts WHERE cik = ? AND taxonomy = ? AND tag = ?"
    result = db.store.select(conn, query, (cik, taxonomy, tag))
    if is_ok(result):
        concepts = result[1]
        return ok(concepts[0]["cid"] if concepts else None)
    else:
        return result


def concept_insert_or_ignore(conn: sqlite3.Connection, cik: str, taxonomy: str, tag: str, name: str) -> Result[int, str]:
    """
    Insert concept if missing and return cid.
    """
    concept_data = [{"cik": cik, "taxonomy": taxonomy, "tag": tag, "name": name}]
    result = db.store.insert_or_ignore(conn, "concepts", concept_data)
    if is_ok(result):
        return concept_get_id(conn, cik, taxonomy, tag)
    else:
        return result


def filing_role_concepts_select(conn: sqlite3.Connection, access_no: str, role_name: str) -> Result[list[dict[str, Any]], str]:
    """
    Get all concepts for a specific filing-role combination.
    Returns full concept records with taxonomy, tag, name.
    """
    query = """
        SELECT  c.cid,
                c.cik,
                c.taxonomy, 
                c.tag,
                c.name
        FROM filing_role_concepts frc
        JOIN filing_roles fr ON frc.rid = fr.rid
        JOIN concepts c ON frc.cid = c.cid
        WHERE fr.access_no = ? AND fr.name = ?
        ORDER BY c.taxonomy, c.tag
        """
    
    return db.store.select(conn, query, (access_no, role_name))


# =============================================================================
# CONTEXT OPERATIONS
# =============================================================================

def context_insert_or_ignore(conn: sqlite3.Connection, start_date: str, end_date: str, mode: str) -> Result[int, str]:
    """
    Insert context if missing and return xid.
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
        return err("context_insert_or_ignore({start_date}, {end_date}, {mode}) : context not found after insert")


# =============================================================================
# UNIT OPERATIONS
# =============================================================================

def unit_insert_or_ignore(conn: sqlite3.Connection, unit_name: str) -> Result[int, str]:
    """
    Insert unit if missing and return unid.
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
        return err("unit_insert_or_ignore({unit_name}) : unit not found after insert")


# =============================================================================
# DEI OPERATIONS
# =============================================================================

def dei_insert_or_ignore(conn: sqlite3.Connection, data: dict[str, Any]) -> Result[int, str]:
    """
    Insert or update DEI data for a filing.
    """
    dei_record = [{
        "access_no": data["access_no"],
        "doc_type": data.get("doc_type"),
        "doc_period_end": data.get("doc_period_end"),
        "fiscal_year": data.get("fiscal_year"),
        "fiscal_month_day_start": data.get("fiscal_month_day_start"),
        "fiscal_month_day_end": data.get("fiscal_month_day_end"),
        "fiscal_period": data.get("fiscal_period")
    }]
    return db.store.insert_or_ignore(conn, "dei", dei_record)

# =============================================================================
# GROUP OPERATIONS
# =============================================================================

def group_insert_or_ignore(conn: sqlite3.Connection, name: str) -> Result[int, str]:
    """
    Insert group if it doesn't exist and return gid.
    """
    group_data = [{"name": name}]
    result = db.store.insert_or_ignore(conn, "groups", group_data)
    if is_not_ok(result):
        return result
    
    # Get the gid (whether newly inserted or existing)
    query = "SELECT gid FROM groups WHERE name = ?"
    result = db.store.select(conn, query, (name,))
    if is_not_ok(result):
        return result
    
    groups = result[1]
    if groups:
        return ok(groups[0]["gid"])
    else:
        return err(f"group_insert_or_ignore({name}): group not found after insert")


def group_get_id(conn: sqlite3.Connection, name: str) -> Result[Optional[int], str]:
    """
    Get gid by name. Returns None if not found.
    """
    query = "SELECT gid FROM groups WHERE name = ?"
    result = db.store.select(conn, query, (name,))
    if is_ok(result):
        groups = result[1]
        return ok(groups[0]["gid"] if groups else None)
    else:
        return result


def group_select(conn: sqlite3.Connection) -> Result[list[dict[str, Any]], str]:
    """
    Get all groups 
    """
    query = "SELECT gid, name as group_name FROM groups ORDER BY name"
    return db.store.select(conn, query)


# =============================================================================
# ROLE PATTERN OPERATIONS
# =============================================================================

def role_pattern_insert_or_ignore(conn: sqlite3.Connection, gid: int, cik: str, pattern: str) -> Result[int, str]:
    """
    Insert role pattern if it doesn't exist, link to group, and return pid.
    """
    # First, insert or get the pattern
    pattern_data = [{"cik": cik, "pattern": pattern}]
    result = db.store.insert_or_ignore(conn, "role_patterns", pattern_data)
    if is_not_ok(result):
        return result
    
    # Get the pid
    query = "SELECT pid FROM role_patterns WHERE cik = ? AND pattern = ?"
    result = db.store.select(conn, query, (cik, pattern))
    if is_not_ok(result):
        return result
    
    patterns = result[1]
    if not patterns:
        return err(f"role_pattern_insert_or_ignore: pattern not found after insert")
    
    pid = patterns[0]["pid"]
    
    # Link to group
    link_data = [{"gid": gid, "pid": pid}]
    result = db.store.insert_or_ignore(conn, "group_role_patterns", link_data)
    if is_not_ok(result):
        return result
    
    return ok(pid)


def role_pattern_select_by_group(conn: sqlite3.Connection, gid: int, cik: str) -> Result[list[dict[str, Any]], str]:
    """
    Get all role patterns for a specific group and company.
    """
    query = """
        SELECT rp.pid, rp.cik, rp.pattern, rp.uid
        FROM role_patterns rp
        JOIN group_role_patterns grp ON rp.pid = grp.pid
        WHERE grp.gid = ? AND rp.cik = ?
        ORDER BY rp.pid
        """
    return db.store.select(conn, query, (gid, cik))


def role_pattern_select(conn: sqlite3.Connection, group_name: str = None, cik: str = None) -> Result[list[dict[str, Any]], str]:
    """
    Get role patterns with optional filters. Includes group name in results.
    """
    base_query = """
        SELECT rp.pid, rp.cik, rp.pattern, rp.uid, g.name as group_name
        FROM role_patterns rp
        JOIN group_role_patterns grp ON rp.pid = grp.pid
        JOIN groups g ON grp.gid = g.gid
        """
    where_clauses = []
    params = []
    
    if group_name:
        where_clauses.append("g.name = ?")
        params.append(group_name)
    
    if cik:
        where_clauses.append("rp.cik = ?")
        params.append(cik)
    
    if where_clauses:
        query = base_query + " WHERE " + " AND ".join(where_clauses)
    else:
        query = base_query
    
    query += " ORDER BY g.name, rp.cik, rp.pid"
    
    return db.store.select(conn, query, tuple(params))


def role_pattern_exists(conn: sqlite3.Connection, pid: int) -> Result[bool, str]:
    """
    Check if a role pattern with given ID exists.
    """
    try:
        query = "SELECT 1 FROM role_patterns WHERE pid = ?"
        cursor = conn.execute(query, (pid,))
        exists = cursor.fetchone() is not None
        cursor.close()
        return ok(exists)
    except sqlite3.Error as e:
        return err(f"queries.role_pattern_exists({pid}) sqlite error: {e}")


def role_pattern_get_details(conn: sqlite3.Connection, pid: int) -> Result[Optional[dict[str, Any]], str]:
    """
    Get role pattern details by ID. Returns None if not found.
    """
    query = """
        SELECT rp.pid, rp.cik, rp.pattern, rp.uid, e.ticker, e.name
        FROM role_patterns rp
        JOIN entities e ON rp.cik = e.cik
        WHERE rp.pid = ?
    """
    result = db.store.select(conn, query, (pid,))
    if is_ok(result):
        patterns = result[1]
        return ok(patterns[0] if patterns else None)
    else:
        return result


def role_pattern_get_by_cik_pattern(conn: sqlite3.Connection, cik: str, pattern: str) -> Result[Optional[dict[str, Any]], str]:
    """
    Get role pattern by CIK and pattern text. Returns None if not found.
    """
    query = "SELECT pid, cik, pattern FROM role_patterns WHERE cik = ? AND pattern = ?"
    result = db.store.select(conn, query, (cik, pattern))
    if is_ok(result):
        patterns = result[1]
        return ok(patterns[0] if patterns else None)
    else:
        return result


def role_pattern_get_by_uid(conn: sqlite3.Connection, cik: str, uid: int) -> Result[Optional[dict[str, Any]], str]:
    """
    Get role pattern by CIK and uid. Returns None if not found.
    """
    query = "SELECT pid, cik, pattern, uid FROM role_patterns WHERE cik = ? AND uid = ?"
    result = db.store.select(conn, query, (cik, uid))
    if is_ok(result):
        patterns = result[1]
        return ok(patterns[0] if patterns else None)
    else:
        return result


def role_pattern_insert_with_uid(conn: sqlite3.Connection, cik: str, pattern: str, uid: int = None) -> Result[int, str]:
    """
    Insert role pattern with optional uid and return pid.
    Uses INSERT (not INSERT OR IGNORE) to catch uid collisions.
    """
    pattern_data = [{"cik": cik, "pattern": pattern, "uid": uid}]
    result = db.store.insert(conn, "role_patterns", pattern_data)
    if is_not_ok(result):
        return result

    # Get the pid - use the unique constraint that succeeded
    if uid is not None:
        query = "SELECT pid FROM role_patterns WHERE cik = ? AND uid = ?"
        result = db.store.select(conn, query, (cik, uid))
    else:
        query = "SELECT pid FROM role_patterns WHERE cik = ? AND pattern = ? AND uid IS NULL"
        result = db.store.select(conn, query, (cik, pattern))

    if is_not_ok(result):
        return result

    patterns = result[1]
    if patterns:
        return ok(patterns[0]["pid"])
    else:
        return err(f"role_pattern_insert_with_uid: pattern not found after insert")


def role_pattern_list_by_cik(conn: sqlite3.Connection, cik: str) -> Result[list[dict[str, Any]], str]:
    """
    List all role patterns for a CIK with uid.
    """
    query = """
        SELECT rp.pid, rp.cik, rp.pattern, rp.uid, e.ticker
        FROM role_patterns rp
        JOIN entities e ON rp.cik = e.cik
        WHERE rp.cik = ?
        ORDER BY rp.uid NULLS LAST, rp.pid
    """
    return db.store.select(conn, query, (cik,))


# =============================================================================
# CONCEPT PATTERN OPERATIONS
# =============================================================================

def concept_pattern_insert_or_ignore(conn: sqlite3.Connection, cik: str, name: str, pattern: str) -> Result[int, str]:
    """
    Insert concept pattern if it doesn't exist and return pid.
    """
    pattern_data = [{"cik": cik, "name": name, "pattern": pattern}]
    result = db.store.insert_or_ignore(conn, "concept_patterns", pattern_data)
    if is_not_ok(result):
        return result
    
    # Get the pid
    query = "SELECT pid FROM concept_patterns WHERE cik = ? AND name = ?"
    result = db.store.select(conn, query, (cik, name))
    if is_not_ok(result):
        return result
    
    patterns = result[1]
    if patterns:
        return ok(patterns[0]["pid"])
    else:
        return err(f"concept_pattern_insert_or_ignore({cik}, {name}): pattern not found after insert")


def group_concept_pattern_insert_or_ignore(conn: sqlite3.Connection, gid: int, pid: int) -> Result[None, str]:
    """
    Link a concept pattern to a group.
    """
    link_data = [{"gid": gid, "pid": pid}]
    result = db.store.insert_or_ignore(conn, "group_concept_patterns", link_data)
    return result if is_not_ok(result) else ok(None)


def concept_pattern_select_by_group(conn: sqlite3.Connection, gid: int, cik: str) -> Result[list[dict[str, Any]], str]:
    """
    Get all concept patterns for a specific group and company.
    """
    query = """
        SELECT cp.pid, cp.cik, cp.name, cp.pattern, cp.uid
        FROM concept_patterns cp
        JOIN group_concept_patterns gcp ON cp.pid = gcp.pid
        WHERE gcp.gid = ? AND cp.cik = ?
        ORDER BY cp.pid
        """
    return db.store.select(conn, query, (gid, cik))


def concept_pattern_select(conn: sqlite3.Connection, group_name: str = None, cik: str = None) -> Result[list[dict[str, Any]], str]:
    """
    Get concept patterns with optional filters. Includes group name in results.
    """
    base_query = """
        SELECT cp.pid, cp.cik, cp.name, cp.pattern, cp.uid, g.name as group_name
        FROM concept_patterns cp
        JOIN group_concept_patterns gcp ON cp.pid = gcp.pid
        JOIN groups g ON gcp.gid = g.gid
        """
    
    where_clauses = []
    params = []
    
    if group_name:
        where_clauses.append("g.name = ?")
        params.append(group_name)
    
    if cik:
        where_clauses.append("cp.cik = ?")
        params.append(cik)
    
    if where_clauses:
        query = base_query + " WHERE " + " AND ".join(where_clauses)
    else:
        query = base_query
    
    query += " ORDER BY g.name, cp.cik, cp.pid"
    
    return db.store.select(conn, query, tuple(params))


def concept_pattern_exists(conn: sqlite3.Connection, pid: int) -> Result[bool, str]:
    """
    Check if a concept pattern with given ID exists.
    """
    try:
        query = "SELECT 1 FROM concept_patterns WHERE pid = ?"
        cursor = conn.execute(query, (pid,))
        exists = cursor.fetchone() is not None
        cursor.close()
        return ok(exists)
    except sqlite3.Error as e:
        return err(f"queries.concept_pattern_exists({pid}) sqlite error: {e}")


def concept_pattern_get_details(conn: sqlite3.Connection, pid: int) -> Result[Optional[dict[str, Any]], str]:
    """
    Get concept pattern details by ID. Returns None if not found.
    """
    query = """
        SELECT cp.pid, cp.cik, cp.name, cp.pattern, cp.uid, e.ticker, e.name as company_name
        FROM concept_patterns cp
        JOIN entities e ON cp.cik = e.cik
        WHERE cp.pid = ?
    """
    result = db.store.select(conn, query, (pid,))
    if is_ok(result):
        patterns = result[1]
        return ok(patterns[0] if patterns else None)
    else:
        return result


def concept_pattern_get_by_cik_name(conn: sqlite3.Connection, cik: str, name: str) -> Result[Optional[dict[str, Any]], str]:
    """
    Get concept pattern by CIK and name. Returns None if not found.
    """
    query = "SELECT pid, cik, name, pattern FROM concept_patterns WHERE cik = ? AND name = ?"
    result = db.store.select(conn, query, (cik, name))
    if is_ok(result):
        patterns = result[1]
        return ok(patterns[0] if patterns else None)
    else:
        return result


def concept_pattern_get_by_uid(conn: sqlite3.Connection, cik: str, uid: int) -> Result[Optional[dict[str, Any]], str]:
    """
    Get concept pattern by CIK and uid. Returns None if not found.
    """
    query = "SELECT pid, cik, name, pattern, uid FROM concept_patterns WHERE cik = ? AND uid = ?"
    result = db.store.select(conn, query, (cik, uid))
    if is_ok(result):
        patterns = result[1]
        return ok(patterns[0] if patterns else None)
    else:
        return result


def concept_pattern_insert_with_uid(conn: sqlite3.Connection, cik: str, name: str, pattern: str, uid: int = None) -> Result[int, str]:
    """
    Insert concept pattern with optional uid and return pid.
    Uses INSERT (not INSERT OR IGNORE) to catch uid collisions.
    """
    pattern_data = [{"cik": cik, "name": name, "pattern": pattern, "uid": uid}]
    result = db.store.insert(conn, "concept_patterns", pattern_data)
    if is_not_ok(result):
        return result

    # Get the pid - (cik, name) is unique
    query = "SELECT pid FROM concept_patterns WHERE cik = ? AND name = ?"
    result = db.store.select(conn, query, (cik, name))
    if is_not_ok(result):
        return result

    patterns = result[1]
    if patterns:
        return ok(patterns[0]["pid"])
    else:
        return err(f"concept_pattern_insert_with_uid: pattern not found after insert")


def concept_pattern_list_by_cik(conn: sqlite3.Connection, cik: str) -> Result[list[dict[str, Any]], str]:
    """
    List all concept patterns for a CIK with uid.
    """
    query = """
        SELECT cp.pid, cp.cik, cp.name, cp.pattern, cp.uid, e.ticker
        FROM concept_patterns cp
        JOIN entities e ON cp.cik = e.cik
        WHERE cp.cik = ?
        ORDER BY cp.uid NULLS LAST, cp.pid
    """
    return db.store.select(conn, query, (cik,))


# =============================================================================
# DYNAMIC CONCEPT MATCHING
# =============================================================================

def select_concept_matches(conn: sqlite3.Connection, gid: int, cik: str, concept_name: str = None, search_field: str = "tag") -> Result[list[dict[str, Any]], str]:
    """
    Dynamically apply concept patterns to cached concepts and return matches.
    Fast because it only applies regex to concepts already cached from probe.
    """
    
    # Get concept patterns to apply
    if concept_name:
        # Get specific pattern
        query = """
            SELECT cp.pid, cp.name, cp.pattern
            FROM concept_patterns cp
            JOIN group_concept_patterns gcp ON cp.pid = gcp.pid
            WHERE gcp.gid = ? AND cp.cik = ? AND cp.name = ?
            """
        result = db.store.select(conn, query, (gid, cik, concept_name))
    else:
        # Get all patterns for this group/company
        result = concept_pattern_select_by_group(conn, gid, cik)
    
    if is_not_ok(result):
        return result
    
    patterns = result[1]
    if not patterns:
        return ok([])  # No patterns defined
    
    # Get available concepts from roles that match this group's role patterns
    # This limits the search to concepts from relevant roles only
    query = """
        SELECT DISTINCT c.cid, c.cik, c.taxonomy, c.tag, c.name as label
        FROM concepts c
        JOIN filing_role_concepts frc ON c.cid = frc.cid
        JOIN filing_roles fr ON frc.rid = fr.rid
        JOIN filings f ON fr.access_no = f.access_no
        WHERE f.cik = ?
        AND EXISTS (
            SELECT 1 FROM group_role_patterns grp
            JOIN role_patterns rp ON grp.pid = rp.pid 
            WHERE grp.gid = ? AND rp.cik = ?
        )
        ORDER BY c.taxonomy, c.tag
        """
    
    result = db.store.select(conn, query, (cik, gid, cik))
    if is_not_ok(result):
        return result
    
    available_concepts = result[1]
    if not available_concepts:
        return ok([])
    
    # Apply each pattern dynamically
    matches = []
    
    for pattern_record in patterns:
        pattern_text = pattern_record["pattern"]
        pattern_name = pattern_record["name"]
        
        try:
            regex = re.compile(pattern_text)
        except re.error as e:
            return err(f"select_concept_matches: invalid regex '{pattern_text}': {e}")
        
        # Apply pattern to available concepts
        for concept in available_concepts:
            if search_field == "tag":
                field_value = concept["tag"]
            else:
                field_value = concept["label"]
            if regex.search(field_value):
                # Add pattern context to the match
                match = dict(concept)
                match["concept_name"] = pattern_name
                match["pattern"] = pattern_text
                matches.append(match)
    
    return ok(matches)


# =============================================================================
# MODIFY OPERATIONS
# =============================================================================

def group_get_by_id(conn: sqlite3.Connection, gid: int) -> Result[dict, str]:
    """Get group by ID."""
    query = "SELECT gid, name as group_name FROM groups WHERE gid = ?"
    result = db.store.select(conn, query, (gid,))
    if is_ok(result):
        groups = result[1]
        if groups:
            return ok(groups[0])
        else:
            return err(f"group_get_by_id: group ID {gid} not found")
    return result


def group_update_name(conn: sqlite3.Connection, gid: int, new_name: str) -> Result[None, str]:
    """Update group name."""
    try:
        query = "UPDATE groups SET name = ? WHERE gid = ?"
        cursor = conn.execute(query, (new_name, gid))
        conn.commit()
        if cursor.rowcount == 0:
            return err(f"group_update_name: no group with ID {gid}")
        cursor.close()
        return ok(None)
    except sqlite3.Error as e:
        return err(f"group_update_name: sqlite error: {e}")


def role_pattern_update(conn: sqlite3.Connection, pid: int, new_pattern: str = None, new_uid: int = None) -> Result[None, str]:
    """Update role pattern regex and/or uid."""
    if not new_pattern and new_uid is None:
        return err("role_pattern_update: must provide new_pattern, new_uid, or both")

    try:
        updates = []
        params = []

        if new_pattern:
            updates.append("pattern = ?")
            params.append(new_pattern)

        if new_uid is not None:
            updates.append("uid = ?")
            params.append(new_uid)

        params.append(pid)
        query = f"UPDATE role_patterns SET {', '.join(updates)} WHERE pid = ?"

        cursor = conn.execute(query, tuple(params))
        conn.commit()
        if cursor.rowcount == 0:
            return err(f"role_pattern_update: no pattern with ID {pid}")
        cursor.close()
        return ok(None)
    except sqlite3.Error as e:
        return err(f"role_pattern_update: sqlite error: {e}")


def concept_pattern_update(conn: sqlite3.Connection, pid: int,
                          new_name: str = None, new_pattern: str = None, new_uid: int = None) -> Result[None, str]:
    """Update concept pattern name, regex, and/or uid."""
    if not new_name and not new_pattern and new_uid is None:
        return err("concept_pattern_update: must provide new_name, new_pattern, new_uid, or combination")

    try:
        updates = []
        params = []

        if new_name:
            updates.append("name = ?")
            params.append(new_name)

        if new_pattern:
            updates.append("pattern = ?")
            params.append(new_pattern)

        if new_uid is not None:
            updates.append("uid = ?")
            params.append(new_uid)

        params.append(pid)
        query = f"UPDATE concept_patterns SET {', '.join(updates)} WHERE pid = ?"

        cursor = conn.execute(query, tuple(params))
        conn.commit()
        if cursor.rowcount == 0:
            return err(f"concept_pattern_update: no pattern with ID {pid}")
        cursor.close()
        return ok(None)
    except sqlite3.Error as e:
        return err(f"concept_pattern_update: sqlite error: {e}")


# =============================================================================
# FACTS IMPORT OPERATIONS
# =============================================================================

def group_role_patterns_match(conn: sqlite3.Connection, cik: str) -> Result[dict[str, list[str]], str]:
    """
    Get role patterns for a company, grouped by group name, matched against actual filing roles.
    Returns: {"Balance": ["StatementOfFinancialPositionClassified"], ...}

    Logic:
      1. Get all groups that have role patterns for this CIK
      2. For each group, get the role patterns (regex)
      3. Match patterns against filing_roles.name from this company's filings
      4. Return dict of {group_name: [matched_role_names]}
    """
    # Get all role patterns for this CIK with their group associations
    query = """
        SELECT g.name as group_name, rp.pattern
        FROM groups g
        JOIN group_role_patterns grp ON g.gid = grp.gid
        JOIN role_patterns rp ON grp.pid = rp.pid
        WHERE rp.cik = ?
        ORDER BY g.name, rp.pattern
    """
    result = db.store.select(conn, query, (cik,))
    if is_not_ok(result):
        return result

    patterns = result[1]
    if not patterns:
        return ok({})

    # Get all role names from filing_roles for this company's filings
    query = """
        SELECT DISTINCT fr.name
        FROM filing_roles fr
        JOIN filings f ON fr.access_no = f.access_no
        WHERE f.cik = ?
    """
    result = db.store.select(conn, query, (cik,))
    if is_not_ok(result):
        return result

    role_names = [row["name"] for row in result[1]]
    if not role_names:
        return ok({})

    # Match patterns against role names
    role_map: dict[str, list[str]] = {}

    for pattern_row in patterns:
        group_name = pattern_row["group_name"]
        pattern = pattern_row["pattern"]

        # Compile regex pattern
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return err(f"group_role_patterns_match: invalid regex pattern '{pattern}': {e}")

        # Find matching role names
        matches = [name for name in role_names if regex.search(name)]

        if matches:
            if group_name not in role_map:
                role_map[group_name] = []
            role_map[group_name].extend(matches)

    # Remove duplicates within each group
    for group_name in role_map:
        role_map[group_name] = list(set(role_map[group_name]))

    return ok(role_map)


def fact_select_past_modes(conn: sqlite3.Connection, cik: str, fiscal_year: str, cid: int, dimensions: dict[str, str]) -> Result[list[dict[str, Any]], str]:
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
        return err(f"fact_select_past_modes: concept {cid} not found")

    tag = result[1][0]["tag"]

    if dimensions:
        # Complex query with dimension matching - match by TAG instead of CID
        # For each fact, check if it has ALL the dimensions with matching members
        query = """
            SELECT DISTINCT ctx.mode, d.fiscal_period
            FROM facts f
            JOIN concepts c ON f.cid = c.cid
            JOIN filing_roles fr ON f.rid = fr.rid
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
            JOIN filing_roles fr ON f.rid = fr.rid
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


def fact_insert_bulk(conn: sqlite3.Connection, facts_list: list[dict[str, Any]]) -> Result[int, str]:
    """
    Bulk insert facts with their dimensions and contexts.
    Returns count of facts inserted.

    For each fact record:
      1. Insert/get context (start_date, end_date, mode) -> xid
      2. Insert/get unit (unit name) -> unid
      3. Get rid from filing_roles (access_no + role)
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
            result = context_insert_or_ignore(conn, str(fact["start_date"]), str(fact["end_date"]), fact["mode"])
            if is_not_ok(result):
                continue  # Skip this fact
            xid = result[1]

            # 2. Get or create unit
            if fact.get("unit"):
                result = unit_insert_or_ignore(conn, fact["unit"])
                if is_not_ok(result):
                    continue
                unid = result[1]
            else:
                # No unit - skip this fact
                continue

            # 3. Get rid from filing_roles
            result = filing_roles_insert_or_ignore(conn, fact["access_no"], fact["role"])
            if is_not_ok(result):
                continue
            rid = result[1]

            # 4. Insert fact
            fact_data = [{
                "rid": rid,
                "cid": fact["cid"],
                "xid": xid,
                "unid": unid,
                "value": fact["value"]
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


# =============================================================================
# STATS OPERATIONS
# =============================================================================

def concept_frequency_analysis(
    conn: sqlite3.Connection,
    cik: str,
    role_filter: list[str],
    min_count: int = 1,
    sort_by: str = "count"
) -> Result[list[dict[str, Any]], str]:
    """
    Analyze concept frequency across filings for a given CIK and role filter.

    Args:
        cik: Company CIK
        role_filter: List of role names to analyze
        min_count: Minimum number of filings (default: 1)
        sort_by: Sort field - "count", "tag", "first", "last" (default: "count")

    Returns:
        List of dicts with:
        - tag: Concept tag name
        - name: Friendly concept name
        - filing_count: How many filings contain it
        - percentage: filing_count / total_filings * 100
        - first_date: Earliest filing date
        - last_date: Latest filing date
    """
    if not role_filter:
        return err("concept_frequency_analysis: role_filter cannot be empty")

    # Get total number of filings with these roles
    placeholders = ",".join("?" * len(role_filter))
    query_total = f"""
        SELECT COUNT(DISTINCT f.access_no) as total
        FROM filings f
        JOIN filing_roles fr ON f.access_no = fr.access_no
        WHERE f.cik = ? AND fr.name IN ({placeholders})
    """
    params_total = [cik] + role_filter

    result = db.store.select(conn, query_total, tuple(params_total))
    if is_not_ok(result):
        return result

    total_filings = result[1][0]["total"] if result[1] else 0
    if total_filings == 0:
        return ok([])

    # Get concept frequency
    query = f"""
        SELECT
            c.tag,
            c.name,
            COUNT(DISTINCT f.access_no) as filing_count,
            MIN(f.filing_date) as first_date,
            MAX(f.filing_date) as last_date
        FROM concepts c
        JOIN facts fa ON c.cid = fa.cid
        JOIN filing_roles fr ON fa.rid = fr.rid
        JOIN filings f ON fr.access_no = f.access_no
        WHERE f.cik = ?
        AND fr.name IN ({placeholders})
        GROUP BY c.tag, c.name
        HAVING filing_count >= ?
    """

    # Build params
    params = [cik] + role_filter + [min_count]

    result = db.store.select(conn, query, tuple(params))
    if is_not_ok(result):
        return result

    stats = result[1]

    # Add percentage calculation
    for stat in stats:
        stat["percentage"] = round((stat["filing_count"] / total_filings) * 100, 1)

    # Sort results
    sort_key_map = {
        "count": lambda x: (-x["filing_count"], x["tag"]),  # Descending count, then tag
        "tag": lambda x: x["tag"],
        "first": lambda x: x["first_date"],
        "last": lambda x: x["last_date"]
    }

    sort_key = sort_key_map.get(sort_by)
    if not sort_key:
        return err(f"concept_frequency_analysis: invalid sort_by '{sort_by}'")

    stats.sort(key=sort_key)

    return ok(stats)
