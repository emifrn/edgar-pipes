import re
import sqlite3
from typing import Any, Optional

from edgar import db
from edgar.result import Result, ok, err, is_ok, is_not_ok


def get_id(conn: sqlite3.Connection, cik: str, taxonomy: str, tag: str) -> Result[Optional[int], str]:
    """
    Get cid for a specific concept by unique key.
    """
    query = "SELECT cid FROM concepts WHERE cik = ? AND taxonomy = ? AND tag = ?"
    result = db.store.select(conn, query, (cik, taxonomy, tag))
    if is_ok(result):
        concepts = result[1]
        return ok(concepts[0]["cid"] if concepts else None)
    else:
        return result


def select_by_entity(conn: sqlite3.Connection, cik: str, taxonomy: Optional[str] = None) -> Result[list[dict[str, Any]], str]:
    """
    Get all concepts cached for an entity, optionally filtered by taxonomy.
    """
    if taxonomy:
        query = "SELECT cid, taxonomy, tag, name FROM concepts WHERE cik = ? AND taxonomy = ? ORDER BY tag"
        return db.store.select(conn, query, (cik, taxonomy))
    else:
        query = "SELECT cid, taxonomy, tag, name FROM concepts WHERE cik = ? ORDER BY taxonomy, tag"
        return db.store.select(conn, query, (cik,))


def select_by_role(conn: sqlite3.Connection, access_no: str, role_name: str) -> Result[list[dict[str, Any]], str]:
    """
    Get all concepts for a specific role in a filing.
    Returns full concept records with taxonomy, tag, name.
    """
    query = """
        SELECT  c.cid,
                c.cik,
                c.taxonomy,
                c.tag,
                c.name
        FROM role_concepts frc
        JOIN roles fr ON frc.rid = fr.rid
        JOIN concepts c ON frc.cid = c.cid
        WHERE fr.access_no = ? AND fr.name = ?
        ORDER BY c.taxonomy, c.tag
        """

    return db.store.select(conn, query, (access_no, role_name))


def select_by_pattern(conn: sqlite3.Connection, gid: int, cik: str, concept_name: Optional[str] = None, search_field: str = "tag") -> Result[list[dict[str, Any]], str]:
    """
    Dynamically apply concept patterns to cached concepts and return matches.
    Fast because it only applies regex to concepts already cached from probe.

    Args:
        gid: Group ID containing concept patterns
        cik: Company CIK
        concept_name: Optional specific pattern name to apply
        search_field: Field to search - "tag" or "name" (label)
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
        result = db.queries.concept_patterns.select_by_group(conn, gid, cik)

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
        JOIN role_concepts frc ON c.cid = frc.cid
        JOIN roles fr ON frc.rid = fr.rid
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
            return err(f"concepts.select_by_pattern: invalid regex '{pattern_text}': {e}")

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


def frequency(
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
        return err("concepts.frequency: role_filter cannot be empty")

    # Get total number of filings with these roles
    placeholders = ",".join("?" * len(role_filter))
    query_total = f"""
        SELECT COUNT(DISTINCT f.access_no) as total
        FROM filings f
        JOIN roles fr ON f.access_no = fr.access_no
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
        JOIN roles fr ON fa.rid = fr.rid
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
        return err(f"concepts.frequency: invalid sort_by '{sort_by}'")

    stats.sort(key=sort_key)

    return ok(stats)
