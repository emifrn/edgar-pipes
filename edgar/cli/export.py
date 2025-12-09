"""
CLI: export

Export database patterns to ep.toml format.

This command reads role patterns, concept patterns, and groups from the database
and generates TOML output suitable for use as an ep.toml configuration file.
It complements the interactive discovery workflow: users explore and create
patterns via CLI commands (ep new, ep add), then export the result for
version control and reproducibility.

The export command reconstructs group hierarchies by analyzing concept set
relationships. Groups that are strict subsets of other groups (within the same
role) are marked as derived groups using the 'from' attribute.
"""
import sys
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

# Local modules
from edgar import db
from edgar import config
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class RoleExport:
    """Role pattern for export."""
    name: str
    pattern: str
    note: Optional[str] = None


@dataclass
class ConceptExport:
    """Concept pattern for export."""
    name: str
    uid: int
    pattern: str
    note: Optional[str] = None


@dataclass
class GroupExport:
    """Group for export with hierarchy info."""
    name: str
    role_name: Optional[str]  # None for derived groups
    concept_uids: set[int]
    from_group: Optional[str] = None  # Parent group name if derived


# =============================================================================
# CLI Interface
# =============================================================================

def add_arguments(subparsers):
    """Add export command to argument parser."""
    parser = subparsers.add_parser(
        "export",
        help="export database patterns to ep.toml format"
    )
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="output file path (default: stdout)"
    )
    parser.add_argument(
        "-t", "--ticker",
        metavar="X",
        help="company ticker (default: from ep.toml)"
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="omit header comments"
    )
    parser.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[None, str]:
    """
    Export database patterns to ep.toml format.

    Args:
        cmd: Command context (unused for this command)
        args: Parsed arguments

    Returns:
        ok(None) on success, err(str) on failure
    """
    # Load workspace configuration
    try:
        root, cfg = config.load_toml()
    except RuntimeError as e:
        return err(f"cli.export.run: {e}")

    db_path = config.get_db_path(root, cfg)
    ticker = args.ticker if args.ticker else config.get_ticker(cfg)

    # Connect to database
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        return err(f"cli.export.run: failed to connect to database: {e}")

    # Get entity CIK
    result = db.queries.entities.select(conn, tickers=[ticker])
    if is_not_ok(result):
        conn.close()
        return err(f"cli.export.run: {result[1]}")

    entities = result[1]
    if not entities:
        conn.close()
        return err(f"cli.export.run: ticker '{ticker}' not found in database")

    entity = entities[0]
    cik = entity["cik"]
    company_name = entity["name"]

    # Collect all data from database
    result = collect_export_data(conn, cik, ticker, company_name, cfg)
    conn.close()

    if is_not_ok(result):
        return result

    roles, concepts, groups = result[1]

    # Reconstruct group hierarchy
    classified_groups = classify_groups(groups)

    # Generate TOML content
    toml_content = generate_toml(
        ticker=ticker,
        cik=cik,
        company_name=company_name,
        cfg=cfg,
        roles=roles,
        concepts=concepts,
        groups=classified_groups,
        include_header=not args.no_header
    )

    # Output
    if args.output:
        try:
            with open(args.output, "w") as f:
                f.write(toml_content)
            print(f"Exported to {args.output}")
        except IOError as e:
            return err(f"cli.export.run: failed to write to {args.output}: {e}")
    else:
        print(toml_content)

    return ok(None)


# =============================================================================
# Data Collection
# =============================================================================

def collect_export_data(
    conn: sqlite3.Connection,
    cik: str,
    ticker: str,
    company_name: str,
    cfg: dict
) -> Result[tuple[list[RoleExport], list[ConceptExport], list[GroupExport]], str]:
    """
    Collect all patterns and groups from database.

    Returns:
        Tuple of (roles, concepts, groups) lists
    """
    # Collect role patterns
    result = db.queries.role_patterns.select(conn, cik=cik)
    if is_not_ok(result):
        return err(f"collect_export_data: failed to query role patterns: {result[1]}")

    roles = []
    role_pid_to_name = {}  # Map pid -> role name for group lookup
    for row in result[1]:
        roles.append(RoleExport(
            name=row["name"],
            pattern=row["pattern"],
            note=row.get("note") if row.get("note") else None
        ))
        role_pid_to_name[row["pid"]] = row["name"]

    # Collect concept patterns
    result = db.queries.concept_patterns.select(conn, cik=cik)
    if is_not_ok(result):
        return err(f"collect_export_data: failed to query concept patterns: {result[1]}")

    concepts = []
    concept_pid_to_uid = {}  # Map pid -> uid for group lookup
    for row in result[1]:
        uid = row.get("uid")
        if uid is None:
            continue  # Skip concepts without UID
        concepts.append(ConceptExport(
            name=row["name"],
            uid=uid,
            pattern=row["pattern"],
            note=row.get("note") if row.get("note") else None
        ))
        concept_pid_to_uid[row["pid"]] = uid

    # Collect groups with their role and concept linkages
    result = db.queries.groups.select(conn)
    if is_not_ok(result):
        return err(f"collect_export_data: failed to query groups: {result[1]}")

    groups = []
    for group_row in result[1]:
        gid = group_row["gid"]
        group_name = group_row["group_name"]

        # Get linked role pattern for this group
        role_name = None
        result = db.queries.role_patterns.select_by_group(conn, gid, cik)
        if is_ok(result) and result[1]:
            # Take the first role (groups typically have one role)
            role_name = result[1][0]["name"]

        # Get linked concept patterns for this group
        result = db.queries.concept_patterns.select_by_group(conn, gid, cik)
        if is_not_ok(result):
            return err(f"collect_export_data: failed to query concepts for group {group_name}: {result[1]}")

        concept_uids = set()
        for cp_row in result[1]:
            uid = cp_row.get("uid")
            if uid is not None:
                concept_uids.add(uid)

        groups.append(GroupExport(
            name=group_name,
            role_name=role_name,
            concept_uids=concept_uids
        ))

    return ok((roles, concepts, groups))


# =============================================================================
# Group Hierarchy Reconstruction
# =============================================================================

def classify_groups(groups: list[GroupExport]) -> list[GroupExport]:
    """
    Classify groups as base or derived by analyzing concept set relationships.

    Algorithm:
    1. Group by role_name (same role = potential parent-child)
    2. For each role cluster, find groups that are strict subsets of others
    3. Assign the smallest superset as parent (most specific ancestor)

    A group is derived if:
    - Its concepts are a STRICT subset of another group's concepts
    - Both groups share the same role

    Returns:
        List of GroupExport with from_group set for derived groups
    """
    if not groups:
        return []

    # Group by role_name
    by_role: dict[Optional[str], list[GroupExport]] = {}
    for group in groups:
        role = group.role_name
        if role not in by_role:
            by_role[role] = []
        by_role[role].append(group)

    result = []

    for role_name, cluster in by_role.items():
        if len(cluster) == 1:
            # Single group in cluster - must be base
            result.append(cluster[0])
            continue

        # Sort by concept count (descending) - largest sets first
        # These are candidates to be base groups
        sorted_cluster = sorted(
            cluster,
            key=lambda g: len(g.concept_uids),
            reverse=True
        )

        # Track which groups have been identified as base groups
        base_groups: list[GroupExport] = []

        for group in sorted_cluster:
            # Find the smallest superset among base groups
            parent = find_smallest_superset(group, base_groups)

            if parent is not None and group.concept_uids < parent.concept_uids:
                # Strict subset - this is a derived group
                derived = GroupExport(
                    name=group.name,
                    role_name=None,  # Derived groups inherit role from parent
                    concept_uids=group.concept_uids,
                    from_group=parent.name
                )
                result.append(derived)
            else:
                # Not a strict subset of any existing base group - this is a base group
                base_groups.append(group)
                result.append(group)

    return result


def find_smallest_superset(
    group: GroupExport,
    candidates: list[GroupExport]
) -> Optional[GroupExport]:
    """
    Find the smallest superset of group's concepts among candidates.

    Returns the candidate with the smallest concept set that still contains
    all of group's concepts. Returns None if no superset exists.
    """
    best_match: Optional[GroupExport] = None
    best_size = float('inf')

    for candidate in candidates:
        # Check if candidate is a superset (contains all of group's concepts)
        if group.concept_uids <= candidate.concept_uids:
            # Prefer smaller supersets (more specific parent)
            if len(candidate.concept_uids) < best_size:
                best_match = candidate
                best_size = len(candidate.concept_uids)

    return best_match


# =============================================================================
# TOML Generation
# =============================================================================

def generate_toml(
    ticker: str,
    cik: str,
    company_name: str,
    cfg: dict,
    roles: list[RoleExport],
    concepts: list[ConceptExport],
    groups: list[GroupExport],
    include_header: bool = True
) -> str:
    """
    Generate ep.toml content from collected data.

    Args:
        ticker: Company ticker symbol
        cik: Company CIK
        company_name: Company name
        cfg: Current ep.toml config (for user_agent, theme, etc.)
        roles: List of role patterns
        concepts: List of concept patterns
        groups: List of groups (with hierarchy info)
        include_header: Whether to include header comments

    Returns:
        TOML-formatted string
    """
    lines = []

    # Header
    if include_header:
        lines.append("# Edgar Pipes Configuration")
        lines.append(f"# Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"# Ticker: {ticker}")
        lines.append("")

    # User preferences
    user_agent = cfg.get("user_agent", "")
    theme = cfg.get("theme", "nobox-minimal")

    lines.append("# User preferences")
    lines.append(f'user_agent = "{user_agent}"')
    lines.append(f'theme = "{theme}"')
    lines.append("")

    # Database and company identification
    database = cfg.get("database", "db/edgar.db")
    cutoff = cfg.get("cutoff", "")

    lines.append("# Database and company identification")
    lines.append(f'database = "{database}"')
    lines.append(f'ticker = "{ticker}"')
    if cutoff:
        lines.append(f'cutoff = "{cutoff}"')
    lines.append("")

    # Roles section
    if roles:
        lines.append("# " + "=" * 77)
        lines.append("# XBRL Roles - Define where to find data in filings")
        lines.append("# " + "=" * 77)
        lines.append("")

        for role in sorted(roles, key=lambda r: r.name):
            lines.append(f"[roles.{_quote_key(role.name)}]")
            lines.append(f'pattern = "{_escape_string(role.pattern)}"')
            if role.note:
                lines.append(f'note = "{_escape_string(role.note)}"')
            lines.append("")

    # Concepts section
    if concepts:
        lines.append("# " + "=" * 77)
        lines.append("# Concepts - Financial metrics to extract")
        lines.append("# " + "=" * 77)
        lines.append("")

        # Sort by UID for consistent output
        for concept in sorted(concepts, key=lambda c: c.uid):
            lines.append(f"[concepts.{_quote_key(concept.name)}]")
            lines.append(f"uid = {concept.uid}")
            lines.append(f'pattern = "{_escape_string(concept.pattern)}"')
            if concept.note:
                lines.append(f'note = "{_escape_string(concept.note)}"')
            lines.append("")

    # Groups section
    if groups:
        lines.append("# " + "=" * 77)
        lines.append("# Groups - Organize concepts for extraction and reporting")
        lines.append("# " + "=" * 77)
        lines.append("")

        # Separate base and derived groups
        base_groups = [g for g in groups if g.from_group is None]
        derived_groups = [g for g in groups if g.from_group is not None]

        # Output base groups first
        if base_groups:
            lines.append("# Main groups (top-level by statement type)")
            for group in sorted(base_groups, key=lambda g: g.name):
                lines.append(f"[groups.{_quote_key(group.name)}]")
                if group.role_name:
                    lines.append(f'role = "{group.role_name}"')
                if group.concept_uids:
                    uid_list = sorted(group.concept_uids)
                    lines.append(f"concepts = {uid_list}")
                lines.append("")

        # Output derived groups
        if derived_groups:
            lines.append("# Derived groups (using 'from' to subset parent groups)")
            for group in sorted(derived_groups, key=lambda g: g.name):
                lines.append(f"[groups.{_quote_key(group.name)}]")
                lines.append(f'from = "{group.from_group}"')
                if group.concept_uids:
                    uid_list = sorted(group.concept_uids)
                    lines.append(f"concepts = {uid_list}")
                lines.append("")

    return "\n".join(lines)


def _quote_key(key: str) -> str:
    """
    Quote a TOML key if it contains special characters.

    TOML bare keys can only contain: A-Za-z0-9_-
    Keys with dots, spaces, or other chars need quoting.
    """
    # Check if key needs quoting
    import re
    if re.match(r'^[A-Za-z0-9_-]+$', key):
        return key
    else:
        return f'"{_escape_string(key)}"'


def _escape_string(s: str) -> str:
    """
    Escape special characters in a TOML string value.
    """
    # Escape backslashes first, then quotes
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\n", "\\n")
    s = s.replace("\t", "\\t")
    return s
