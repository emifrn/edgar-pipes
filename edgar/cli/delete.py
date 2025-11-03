"""
CLI: delete

Pure action command that deletes records based on piped data type.
Default behavior is dry-run (returns preview data).
Use --yes flag to perform actual deletion (returns results data).
"""

import sys
import sqlite3
from typing import Any
from collections import defaultdict

# Local modules
from edgar import db
from edgar import cli
from edgar import xbrl
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


def add_arguments(subparsers):
    """Add delete command to argument parser."""
    parser_delete = subparsers.add_parser("delete", help="delete records from piped data")
    parser_delete.add_argument("-y", "--yes", action="store_true", help="perform actual deletion (default: dry-run)")
    parser_delete.set_defaults(func=run)


def _preview_entities(entities: list[dict]) -> list[dict]:
    """Generate preview data for entity deletion."""
    return [{
        "operation": "delete_entity",
        "ticker": entity["ticker"].upper(),
        "cik": entity["cik"],
        "name": entity["name"],
        "status": "dry-run",
    } for entity in entities]


def _delete_entities(conn: sqlite3.Connection, entities: list[dict]) -> Result[list[dict], str]:
    """Delete entities and return results."""
    results = []
    
    for entity in entities:
        cik = entity["cik"]
        result = db.store.delete(conn, "entities", "cik", [cik])
        if is_not_ok(result):
            return err(f"cli.delete._delete_entities: failed to delete company {entity['ticker']}: {result[1]}")
        
        results.append({
            "operation": "delete_entity", 
            "ticker": entity["ticker"].upper(),
            "cik": cik,
            "name": entity["name"],
            "status": "deleted"
        })
    
    return ok(results)


def _preview_filings(filings: list[dict]) -> list[dict]:
    """Generate preview data for filing deletion."""
    return [{
        "operation": "delete_filing",
        "access_no": filing.get("access_no", "???"),
        "ticker": filing.get("ticker", "???"),
        "filing_date": filing.get("filing_date", "unknown"),
        "form_type": filing.get("form_type", "???"),
        "status": "dry-run",
    } for filing in filings]


def _delete_filings(conn: sqlite3.Connection, filings: list[dict]) -> Result[list[dict], str]:
    """Delete filings and return results."""
    results = []
    
    for filing in filings:
        access_no = filing.get("access_no")
        if not access_no:
            continue
            
        result = db.store.delete(conn, "filings", "access_no", [access_no])
        if is_not_ok(result):
            return err(f"cli.delete._delete_filings: failed to delete filing {access_no}: {result[1]}")
        
        results.append({
            "operation": "delete_filing",
            "access_no": access_no,
            "ticker": filing.get("ticker", "???"),
            "filing_date": filing.get("filing_date", "unknown"),
            "form_type": filing.get("form_type", "???"),
            "status": "deleted",
        })
    
    return ok(results)


def _preview_roles(roles: list[dict]) -> list[dict]:
    """Generate preview data for role deletion."""
    return [{
        "operation": "delete_role",
        "access_no": role.get("access_no", "???"),
        "ticker": role.get("ticker", "???"),
        "role_name": role.get("role_name", "???"),
        "status": "dry-run",
    } for role in roles]


def _delete_roles(conn: sqlite3.Connection, roles: list[dict]) -> Result[list[dict], str]:
    """Delete roles and return results."""
    results = []
    
    for role in roles:
        access_no = role.get("access_no")
        role_name = role.get("role_name")
        if not access_no or not role_name:
            continue
            
        # Look up rid
        query = "SELECT rid FROM roles WHERE access_no = ? AND name = ?"
        result = db.store.select(conn, query, (access_no, role_name))
        if is_not_ok(result) or not result[1]:
            continue

        rid = result[1][0]["rid"]
        result = db.store.delete(conn, "roles", "rid", [rid])
        if is_not_ok(result):
            return err(f"cli.delete._delete_roles: failed to delete role {role_name}: {result[1]}")
        
        results.append({
            "operation": "delete_role",
            "access_no": access_no,
            "ticker": role.get("ticker", "???"),
            "role_name": role_name,
            "status": "deleted",
        })
    
    return ok(results)


def _preview_concepts(concepts: list[dict]) -> list[dict]:
    """Generate preview data for concept deletion."""
    # Build summary by company and taxonomy
    summary = defaultdict(lambda: defaultdict(int))
    
    for concept in concepts:
        cik = concept.get("cik", "unknown")
        company = f"CIK-{cik}"
        
        # Get friendly taxonomy name
        taxonomy = concept.get("taxonomy", "unknown")
        taxonomy_name = xbrl.facts.taxonomy_name(taxonomy)
        
        summary[company][taxonomy_name] += 1
    
    # Convert to list of records
    preview_data = []
    for company in sorted(summary.keys()):
        for taxonomy in sorted(summary[company].keys()):
            count = summary[company][taxonomy]
            preview_data.append({
                "operation": "delete_concepts",
                "company": company,
                "taxonomy": taxonomy,
                "count": count,
                "status": "dry-run",
            })
    
    return preview_data


def _delete_concepts(conn: sqlite3.Connection, concepts: list[dict]) -> Result[list[dict], str]:
    """Delete concepts and return results."""
    # Build summary for results
    summary = defaultdict(lambda: defaultdict(int))
    concept_ids = []
    
    for concept in concepts:
        cid = concept.get("cid")
        if cid:
            concept_ids.append(cid)
        
        cik = concept.get("cik", "unknown")
        result = db.queries.entities.get(conn, cik=cik)
        if is_ok(result) and result[1]:
            company = result[1]["ticker"].upper()
        else:
            company = f"CIK-{cik}"
        
        taxonomy = concept.get("taxonomy", "unknown")
        taxonomy_name = xbrl.facts.taxonomy_name(taxonomy)
        summary[company][taxonomy_name] += 1
    
    # Perform deletion
    if concept_ids:
        result = db.store.delete(conn, "concepts", "cid", concept_ids)
        if is_not_ok(result):
            return err(f"cli.delete._delete_concepts: failed to delete concepts: {result[1]}")
    
    # Build results
    results = []
    for company in sorted(summary.keys()):
        for taxonomy in sorted(summary[company].keys()):
            deleted = summary[company][taxonomy]
            results.append({
                "operation": "delete_concepts",
                "company": company,
                "taxonomy": taxonomy,
                "deleted": deleted,
                "status": "deleted"
            })
    
    return ok(results)

def _preview_groups(groups: list[dict]) -> list[dict]:
    """Generate preview data for group deletion."""
    return [{
        "operation": "delete_group",
        "gid": group["gid"],
        "group_name": group["group_name"],
        "status": "dry-run",
    } for group in groups]


def _delete_groups(conn: sqlite3.Connection, groups: list[dict]) -> Result[list[dict], str]:
    """Delete groups and return results."""
    results = []

    for group in groups:
        gid = group["gid"]
        group_name = group["group_name"]

        result = db.store.delete(conn, "groups", "gid", [gid])
        if is_not_ok(result):
            return err(f"cli.delete._delete_groups: failed to delete group {group_name}: {result[1]}")

        results.append({
            "operation": "delete_group",
            "gid": gid,
            "group_name": group_name,
            "status": "deleted"
        })

    return ok(results)


def _preview_patterns(patterns: list[dict]) -> list[dict]:
    """Generate preview data for pattern deletion."""
    preview_data = []
    
    for pattern in patterns:
        if pattern.get("type") == "role":
            preview_data.append({
                "operation": "delete_role_pattern",
                "uid": pattern.get("uid"),
                "group_name": pattern["group_name"],
                "pattern": pattern["pattern"],
                "status": "dry-run",
            })
        else:  # concept pattern
            preview_data.append({
                "operation": "delete_concept_pattern",
                "uid": pattern.get("uid"),
                "name": pattern["name"],
                "pattern": pattern["pattern"],
                "status": "dry-run",
            })
    
    return preview_data


def _delete_patterns(conn: sqlite3.Connection, patterns: list[dict]) -> Result[list[dict], str]:
    """Delete patterns and return results."""
    results = []

    for pattern in patterns:
        pid = pattern["pid"]

        if pattern.get("type") == "role":
            # Delete role pattern
            result = db.store.delete(conn, "role_patterns", "pid", [pid])
            if is_not_ok(result):
                return err(f"cli.delete._delete_patterns: failed to delete role pattern {pid}: {result[1]}")

            results.append({
                "operation": "delete_role_pattern",
                "uid": pattern.get("uid"),
                "group_name": pattern["group_name"],
                "pattern": pattern["pattern"],
                "status": "deleted"
            })
        else:
            # Delete concept pattern (also removes group linkages due to FK CASCADE)
            result = db.store.delete(conn, "concept_patterns", "pid", [pid])
            if is_not_ok(result):
                return err(f"cli.delete._delete_patterns: failed to delete concept pattern {pid}: {result[1]}")

            results.append({
                "operation": "delete_concept_pattern",
                "uid": pattern.get("uid"),
                "name": pattern["name"],
                "pattern": pattern["pattern"],
                "status": "deleted"
            })

    return ok(results)


def _preview_facts(facts: list[dict]) -> list[dict]:
    """Generate preview data for fact deletion."""
    fact_count = len([f for f in facts if f.get("fid")])
    return [{
        "operation": "delete_facts",
        "count": fact_count,
        "status": "dry-run",
    }]


def _delete_facts(conn: sqlite3.Connection, facts: list[dict]) -> Result[list[dict], str]:
    """Delete facts and return results."""
    fact_ids = [f.get("fid") for f in facts if f.get("fid")]

    if fact_ids:
        result = db.store.delete(conn, "facts", "fid", fact_ids)
        if is_not_ok(result):
            return err(f"cli.delete._delete_facts: failed to delete facts: {result[1]}")
    
    return ok([{
        "operation": "delete_facts",
        "deleted": len(fact_ids),
        "status": "deleted"
    }])


def run(cmd: Cmd, args) -> Result[Cmd | None, str]:
    """Delete records based on piped data type. Default: dry-run, --yes: actual deletion."""
    
    try:
        if not cmd["data"]:
            return err("cli.delete.run: no data received from stdin. Use: command | delete")
        
        delete = {"entities": _delete_entities,   
                  "filings": _delete_filings,     
                  "roles": _delete_roles,         
                  "concepts": _delete_concepts,   
                  "facts": _delete_facts,
                  "groups": _delete_groups,
                  "patterns": _delete_patterns}

        preview = {"entities": _preview_entities,   
                   "filings": _preview_filings,     
                   "roles": _preview_roles,         
                   "concepts": _preview_concepts,   
                   "facts": _preview_facts,
                   "groups": _preview_groups,
                   "patterns": _preview_patterns}
        
        if cmd["name"] in delete:
            if args.yes:
                conn = sqlite3.connect(args.db)
                result = db.store.init(conn)
                if is_not_ok(result):
                    conn.close()
                    return result
                result = delete[cmd["name"]](conn, cmd["data"])
                conn.close()
                return ok({"name": "delete_result", "data": result[1]})
            else:
                preview_data = preview[cmd["name"]](cmd["data"])
                return ok({"name": "delete_preview", "data": preview_data})
        else:
            name = cmd["name"]
            return err(f"cli.delete.run: unknown name received: {name}. Cannot determine what to delete.")
        
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.delete.run: {e}")
