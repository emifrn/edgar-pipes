"""
CLI: report

Generate financial reports from extracted facts.
Pivots facts to wide format (periods × concepts).
"""
import re
import sys
import sqlite3
from typing import Any
from collections import defaultdict

# Local
from edgar import config
from edgar import db
from edgar import config
from edgar import db
from edgar import cli
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


def add_arguments(subparsers):
    """Add report command to argument parser."""
    parser_report = subparsers.add_parser("report", help="generate financial reports from facts")
    parser_report.add_argument("-t", "--ticker", metavar="X", help="company ticker symbol")
    parser_report.add_argument("-g", "--group", metavar="X", required=True, help="group name (required)")
    parser_report.add_argument("-d", "--date", metavar='X', nargs="+", help="filter facts by end date constraints ('>2024-01-01', '<=2024-12-31')")
    parser_report.add_argument("-c", "--cols", metavar='X', nargs="+", help="filter output columns")

    # Period filtering - mutually exclusive
    period_group = parser_report.add_mutually_exclusive_group()
    period_group.add_argument("-q", "--quarterly", action="store_true", help="show only quarterly data (Q1, Q2, Q3, Q4)")
    period_group.add_argument("-y", "--yearly", action="store_true", help="show only annual data (FY)")

    # Mode filtering - mutually exclusive
    mode_group = parser_report.add_mutually_exclusive_group()
    mode_group.add_argument("-i", "--instant", action="store_true", help="show only instant/point-in-time measurements (balance sheet items)")
    mode_group.add_argument("-f", "--flow", action="store_true", help="show only flow/period measurements (income statement items)")

    # Scaling option
    parser_report.add_argument("-s", "--scale",
                              choices=["auto", "B", "M", "K"],
                              default="auto",
                              help="scale numeric values: auto (detect, default), B (billions), M (millions), K (thousands)")

    parser_report.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Generate financial report from facts.

    Args:
        cmd: Piped data (optional)
        args: Command arguments

    Returns:
        ok(Cmd) - Report data in wide format
        err(str) - Error occurred
    """
    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row

    try:
        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result

        # Get CIK from piped data or explicit ticker or default ticker
        explicit_ciks = []

        # Priority 1: Explicit ticker from command line
        # Priority 2: Default ticker from ft.toml (if no explicit ticker)
        ticker = args.ticker if args.ticker else (
            args.default_ticker if hasattr(args, 'default_ticker') and args.default_ticker else None
        )

        if ticker:
            result = db.queries.entities.select(conn, [ticker])
            if is_not_ok(result):
                conn.close()
                return result

            entities = result[1]
            if not entities:
                conn.close()
                return err(f"ticker '{ticker}' not found")

            explicit_ciks = [e["cik"] for e in entities]

        # Priority 3: Merge with piped CIKs
        ciks = cli.shared.merge_stdin_field("cik", cmd["data"], explicit_ciks)

        if not ciks:
            conn.close()
            return err("report: no companies specified (use -t or pipe from select)")

        if len(ciks) > 1:
            conn.close()
            return err("report: multiple companies not supported (select one company)")

        cik = ciks[0]

        # Validate group exists
        if not args.group:
            conn.close()
            return err("report: --group is required")

        # Get facts for this CIK and group
        date_filters = cli.shared.parse_date_constraints(args.date, 'end_date')
        result = _get_facts_for_group(conn, cik, args.group, date_filters)
        if is_not_ok(result):
            conn.close()
            return result

        facts = result[1]
        if not facts:
            conn.close()
            return ok({"name": "report", "data": []})

        # Pivot to wide format
        result = _pivot_facts(facts)
        if is_not_ok(result):
            conn.close()
            return result

        pivoted = result[1]

        # Derive Q4 automatically
        pivoted = _derive_q4(pivoted, facts)

        # Filter by period type if requested
        if args.quarterly:
            pivoted = _filter_quarterly(pivoted)
        elif args.yearly:
            pivoted = _filter_yearly(pivoted)

        # Filter by mode if requested
        if args.instant:
            pivoted = _filter_mode(pivoted, "instant")
        elif args.flow:
            pivoted = _filter_mode(pivoted, "flow")

        # Filter columns if requested
        if args.cols:
            pivoted = _filter_columns(pivoted, args.cols)

        # Apply scaling if requested
        if args.scale:
            pivoted = _apply_scale(pivoted, args.scale)

        conn.close()
        return ok({"name": "report", "data": pivoted})

    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.report.run: {e}")


def _get_facts_for_group(
    conn: sqlite3.Connection,
    cik: str,
    group_name: str,
    date_filters: list[tuple[str, str, str]] | None
) -> Result[list[dict[str, Any]], str]:
    """
    Get all facts for a CIK and group.

    Returns list of dicts with:
    - concept_name: semantic name from concept_patterns
    - fiscal_year: year
    - fiscal_period: Q1/Q2/Q3/FY
    - value: numeric value
    - mode: instant/quarter/semester/threeQ/year
    """
    # Get group ID
    query = "SELECT gid FROM groups WHERE name = ?"
    result = db.store.select(conn, query, (group_name,))
    if is_not_ok(result):
        return result

    rows = result[1]
    if not rows:
        return err(f"group '{group_name}' not found")

    group_id = rows[0]["gid"]

    # Get concept patterns for this group
    query = """
        SELECT cp.name, cp.pattern
        FROM concept_patterns cp
        JOIN group_concept_patterns gcp ON cp.pid = gcp.pid
        WHERE gcp.gid = ? AND cp.cik = ?
    """
    result = db.store.select(conn, query, (group_id, cik))
    if is_not_ok(result):
        return result

    patterns = result[1]
    if not patterns:
        return ok([])  # No patterns defined for this group

    # Get all concepts for this CIK
    query = "SELECT cid, tag, balance FROM concepts WHERE cik = ?"
    result = db.store.select(conn, query, (cik,))
    if is_not_ok(result):
        return result

    all_concepts = result[1]

    # Match concepts to patterns and build tag->pattern_name mapping
    tag_to_pattern_name: dict[str, str] = {}
    matched_concept_ids: set[int] = set()

    for concept_row in all_concepts:
        cid = concept_row["cid"]
        tag = concept_row["tag"]

        # Try to match against each pattern
        for pattern_row in patterns:
            pattern_name = pattern_row["name"]
            pattern = pattern_row["pattern"]

            try:
                regex = re.compile(pattern)
                if regex.search(tag):
                    tag_to_pattern_name[tag] = pattern_name
                    matched_concept_ids.add(cid)
                    break  # Found a match, stop checking other patterns
            except re.error:
                continue  # Skip invalid patterns

    if not matched_concept_ids:
        return ok([])  # No concepts matched any patterns

    # Query facts for matched concepts
    placeholders = ",".join("?" * len(matched_concept_ids))
    query = f"""
        SELECT
            c.cid,
            c.tag,
            c.balance,
            d.fiscal_year,
            d.fiscal_period,
            f.value,
            f.decimals,
            ctx.mode,
            ctx.end_date
        FROM facts f
        JOIN roles fr ON f.rid = fr.rid
        JOIN filings fi ON fr.access_no = fi.access_no
        JOIN dei d ON fi.access_no = d.access_no
        JOIN concepts c ON f.cid = c.cid
        JOIN contexts ctx ON f.xid = ctx.xid
        WHERE fi.cik = ?
          AND c.cid IN ({placeholders})
    """

    params = [cik] + list(matched_concept_ids)

    # Add date filters if specified
    if date_filters:
        for field, operator, value in date_filters:
            query += f" AND ctx.{field} {operator} ?"
            params.append(value)

    query += " ORDER BY d.fiscal_year, d.fiscal_period, c.tag"

    result = db.store.select(conn, query, params)
    if is_not_ok(result):
        return result

    fact_rows = result[1]

    # Map tags to pattern names in the output
    facts = []
    for row in fact_rows:
        tag = row["tag"]
        pattern_name = tag_to_pattern_name.get(tag)
        if pattern_name:  # Should always be true, but safety check
            facts.append({
                "concept_name": pattern_name,  # Use semantic name from pattern
                "fiscal_year": row["fiscal_year"],
                "fiscal_period": row["fiscal_period"],
                "value": row["value"],
                "decimals": row["decimals"],
                "mode": row["mode"],
                "end_date": row["end_date"]
            })

    return ok(facts)


def _pivot_facts(facts: list[dict[str, Any]]) -> Result[list[dict[str, Any]], str]:
    """
    Pivot facts to wide format: periods × concepts.

    Each row represents a fiscal period with concept values as columns.
    Uses mode to distinguish between quarter vs YTD data:
    - quarter mode -> Q1, Q2, Q3 (standalone quarters)
    - semester mode -> 6M YTD (not implemented by most companies)
    - threeQ mode -> 9M YTD (9-month year-to-date, NOT Q3 quarter)
    - year mode -> FY
    """
    # Collect all unique concept names for column consistency
    all_concepts = set()
    concept_decimals: dict[str, str] = {}  # Track decimals per concept
    concept_balance: dict[str, str | None] = {}  # Track balance per concept
    concept_tag: dict[str, str] = {}  # Track tag per concept for average detection

    for fact in facts:
        concept_name = fact["concept_name"]
        all_concepts.add(concept_name)
        # Store the first decimals value seen for each concept (should be consistent)
        if concept_name not in concept_decimals and fact.get("decimals"):
            concept_decimals[concept_name] = fact["decimals"]
        # Store balance attribute (debit/credit/None)
        if concept_name not in concept_balance:
            concept_balance[concept_name] = fact.get("balance")
        # Store tag for average detection
        if concept_name not in concept_tag:
            concept_tag[concept_name] = fact.get("tag", "")

    # Group facts by (fiscal_year, fiscal_period, mode) to distinguish threeQ from Q3 quarter
    period_data: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(dict)

    for fact in facts:
        fiscal_year = fact["fiscal_year"]
        fiscal_period = fact["fiscal_period"]
        mode = fact["mode"]
        concept_name = fact["concept_name"]
        value = fact["value"]

        # Create period label based on mode, not just fiscal_period
        # This distinguishes between "Q3 quarter" vs "9M YTD" which both have fiscal_period="Q3"
        if mode == "threeQ":
            period_label = "9M YTD"
        elif mode == "semester":
            period_label = "6M YTD"
        elif mode == "year":
            period_label = "FY"
        elif mode == "quarter":
            period_label = fiscal_period  # Q1, Q2, Q3
        elif mode == "instant":
            period_label = fiscal_period  # Use fiscal_period for balance sheet items
        else:
            period_label = fiscal_period  # Fallback

        period_key = (fiscal_year, period_label, mode)
        period_data[period_key][concept_name] = value

    # Convert to list of dicts, ensuring all concepts appear as columns
    pivoted = []
    for (fiscal_year, period_label, mode), concept_values in sorted(period_data.items()):
        # Normalize mode to semantic measurement type
        normalized_mode = "instant" if mode == "instant" else "flow"

        row = {
            "fiscal_year": fiscal_year,
            "fiscal_period": period_label,
            "mode": normalized_mode,
            "_concept_decimals": concept_decimals,  # Store metadata for scaling
            "_concept_balance": concept_balance,  # Store balance metadata for Q4 derivation
            "_concept_tag": concept_tag,  # Store tags for average detection
        }
        # Add all concepts as columns, even if missing (will be None)
        for concept_name in sorted(all_concepts):
            row[concept_name] = concept_values.get(concept_name)

        pivoted.append(row)

    return ok(pivoted)


def _round_to_decimals(value: float, decimals: str | None) -> float:
    """
    Round a derived value to match XBRL decimal precision.

    Args:
        value: The calculated value to round
        decimals: XBRL decimals attribute (e.g., "2", "-3", "INF")

    Returns:
        Rounded value matching the filed precision
    """
    if decimals is None or decimals == "INF":
        return value  # No rounding needed

    try:
        dec_int = int(decimals)
    except (ValueError, TypeError):
        return value  # Can't parse, return as-is

    # Positive decimals: round to that many decimal places
    if dec_int >= 0:
        return round(value, dec_int)

    # Negative decimals: value is pre-scaled, round to integers
    # (e.g., decimals=-3 means value in thousands, round to nearest thousand)
    return round(value)


def _derive_q4(pivoted: list[dict[str, Any]], facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Derive Q4 values automatically when possible.

    Logic:
    - Stock variables (mode="instant"): Copy FY value to Q4
    - Flow variables: Calculate Q4 = FY - 9M_YTD (if 9M YTD exists)
                      OR Q4 = FY - (Q1 + Q2 + Q3) (if all quarters exist)

    Note: Most companies report Q1 quarter + 9M YTD + FY, so we can derive Q4 = FY - 9M_YTD
    """
    # Determine which concepts are stock (instant) vs flow (period-based)
    concept_modes: dict[str, str] = {}
    for fact in facts:
        concept_name = fact["concept_name"]
        mode = fact["mode"]
        if concept_name not in concept_modes:
            concept_modes[concept_name] = mode
        elif mode == "instant":
            # If we see instant mode for this concept, it's a stock variable
            concept_modes[concept_name] = "instant"

    # Get all unique concept names to ensure consistent columns
    all_concepts = set()
    metadata_keys = ("fiscal_year", "fiscal_period", "mode", "_concept_decimals", "_concept_balance", "_concept_tag")
    for row in pivoted:
        for key in row.keys():
            if key not in metadata_keys:
                all_concepts.add(key)

    # Group pivoted data by fiscal year
    year_data: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    for row in pivoted:
        fiscal_year = row["fiscal_year"]
        fiscal_period = row["fiscal_period"]
        year_data[fiscal_year][fiscal_period] = row

    # Derive Q4 for each year
    output = list(pivoted)  # Start with original data

    for fiscal_year, periods in year_data.items():
        if "FY" not in periods:
            continue  # Need FY to derive Q4

        fy_row = periods["FY"]
        q1_row = periods.get("Q1", {})
        q2_row = periods.get("Q2", {})
        q3_row = periods.get("Q3", {})
        ytd_9m_row = periods.get("9M YTD", {})

        # Get metadata for Q4 derivation
        concept_decimals = fy_row.get("_concept_decimals", {})
        concept_balance = fy_row.get("_concept_balance", {})
        concept_tag = fy_row.get("_concept_tag", {})

        # Create Q4 row with all concepts initialized to None
        q4_row = {
            "fiscal_year": fiscal_year,
            "fiscal_period": "Q4",
            "mode": "flow",  # Will be updated below if all concepts are instant
            "_concept_decimals": concept_decimals,
            "_concept_balance": concept_balance,
            "_concept_tag": concept_tag,
        }
        for concept_name in all_concepts:
            q4_row[concept_name] = None

        # Track if we have any flow variables
        has_flow = False
        has_stock = False

        # For each concept, try to derive Q4
        for concept_name in all_concepts:
            fy_value = fy_row.get(concept_name)
            if fy_value is None:
                continue  # Can't derive without FY value

            # Check if this is a stock variable (instant mode)
            is_stock = concept_modes.get(concept_name) == "instant"

            if is_stock:
                # Stock variable (balance sheet): copy FY value
                q4_row[concept_name] = fy_value
                has_stock = True
            else:
                # Flow variable: determine if derivable or should copy FY
                has_flow = True

                # Get concept metadata
                balance = concept_balance.get(concept_name)
                tag = concept_tag.get(concept_name, "")

                # Decide derivation strategy based on XBRL metadata:
                # 1. If balance is debit/credit → cumulative flow (revenue, expenses) → derive Q4
                # 2. If tag contains "average" → weighted average → copy FY value
                # 3. Otherwise → default to derivation (handles EPS, ratios)

                should_derive = True
                if balance in ("debit", "credit"):
                    # Cumulative flow: derive Q4 by subtraction
                    should_derive = True
                elif "average" in tag.lower():
                    # Weighted average or similar: copy FY value
                    should_derive = False
                else:
                    # Default: derive (handles EPS and other ratios)
                    should_derive = True

                if not should_derive:
                    # Copy FY value (weighted averages)
                    q4_row[concept_name] = fy_value
                else:
                    # Derive Q4 by subtraction
                    derived_value = None

                    # Option 1: Use 9M YTD if available (most common case)
                    ytd_9m_val = ytd_9m_row.get(concept_name)
                    if ytd_9m_val is not None:
                        derived_value = fy_value - ytd_9m_val
                    else:
                        # Option 2: Use Q1 + Q2 + Q3 if all are available
                        q1_val = q1_row.get(concept_name)
                        q2_val = q2_row.get(concept_name)
                        q3_val = q3_row.get(concept_name)

                        if q1_val is not None and q2_val is not None and q3_val is not None:
                            derived_value = fy_value - (q1_val + q2_val + q3_val)
                        # Otherwise leave as None (can't derive)

                    # Round derived value to match filed precision
                    if derived_value is not None:
                        q4_row[concept_name] = _round_to_decimals(derived_value, concept_decimals.get(concept_name))

        # Set mode based on what types of concepts we derived
        # If only stock variables (instant), mark as instant
        # Otherwise mark as flow (including mixed stock+flow cases)
        if has_stock and not has_flow:
            q4_row["mode"] = "instant"

        output.append(q4_row)

    # Sort output by year and period
    period_order = {"Q1": 1, "Q2": 2, "Q3": 3, "6M YTD": 4, "9M YTD": 5, "Q4": 6, "FY": 7}
    output.sort(key=lambda x: (x["fiscal_year"], period_order.get(x["fiscal_period"], 99)))

    return output


def _filter_quarterly(pivoted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Filter to only quarterly periods (Q1, Q2, Q3, Q4).
    Excludes YTD periods (6M YTD, 9M YTD) and FY.
    """
    quarterly_periods = {"Q1", "Q2", "Q3", "Q4"}
    return [row for row in pivoted if row["fiscal_period"] in quarterly_periods]


def _filter_yearly(pivoted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Filter to only annual periods (FY).
    """
    return [row for row in pivoted if row["fiscal_period"] == "FY"]


def _filter_mode(pivoted: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    """
    Filter by measurement type.

    Args:
        mode: "instant" for point-in-time values, "flow" for period changes

    Returns:
        Filtered rows matching the specified mode type
    """
    return [row for row in pivoted if row["mode"] == mode]


def _filter_columns(pivoted: list[dict[str, Any]], cols: list[str]) -> list[dict[str, Any]]:
    """
    Filter output to only include specified columns (plus fiscal_year/fiscal_period/mode).
    """
    filtered = []
    for row in pivoted:
        filtered_row = {
            "fiscal_year": row["fiscal_year"],
            "fiscal_period": row["fiscal_period"],
            "mode": row["mode"]
        }
        for col in cols:
            if col in row:
                filtered_row[col] = row[col]
        filtered.append(filtered_row)

    return filtered


def _detect_scale(pivoted: list[dict[str, Any]]) -> str:
    """
    Auto-detect appropriate scale based on maximum absolute value in numeric columns.

    Returns:
        "B" for billions (max >= 1e9)
        "M" for millions (max >= 1e6)
        "K" for thousands (max >= 1e3)
        "" for no scaling (max < 1e3)
    """
    metadata_cols = {"fiscal_year", "fiscal_period", "mode"}
    max_value = 0

    for row in pivoted:
        for key, value in row.items():
            if key in metadata_cols:
                continue
            if isinstance(value, (int, float)) and value is not None:
                max_value = max(max_value, abs(value))

    if max_value >= 1e9:
        return "B"
    elif max_value >= 1e6:
        return "M"
    elif max_value >= 1e3:
        return "K"
    else:
        return ""


def _apply_scale(pivoted: list[dict[str, Any]], scale_choice: str) -> list[dict[str, Any]]:
    """
    Apply XBRL-native scaling with column headers indicating scale.

    Uses decimals from XBRL to determine native scale for each concept:
    - Negative decimals (-3, -6, -9): Value is pre-scaled, use XBRL scale
    - Positive decimals or INF: Value is NOT scaled (per-share, ratios)

    Args:
        pivoted: Report data rows (includes _concept_decimals metadata)
        scale_choice: "auto" (use XBRL-native) or override scale "B"/"M"/"K"

    Returns:
        Formatted data with scale indicators in column headers
    """
    # Metadata columns that should not be processed
    metadata_cols = {"fiscal_year", "fiscal_period", "mode", "_concept_decimals", "_concept_balance", "_concept_tag"}

    # Build formatted output
    formatted = []
    for row in pivoted:
        concept_decimals = row.get("_concept_decimals", {})
        formatted_row = {}

        # Add metadata columns with renamed headers
        formatted_row["FY"] = row.get("fiscal_year")
        formatted_row["Period"] = row.get("fiscal_period")
        formatted_row["Mode"] = row.get("mode")

        # Process each concept column
        for key, value in row.items():
            if key in metadata_cols:
                continue  # Skip metadata

            # Determine scale for this concept from XBRL decimals
            decimals = concept_decimals.get(key)
            scale_suffix = _get_scale_suffix_from_decimals(decimals, scale_choice)

            # Add column with scale suffix in header
            column_name = f"{key} ({scale_suffix})" if scale_suffix else key
            formatted_row[column_name] = value

        formatted.append(formatted_row)

    return formatted


def _get_scale_suffix_from_decimals(decimals: str | None, scale_override: str) -> str:
    """
    Determine scale suffix for column header based on XBRL decimals.

    Args:
        decimals: XBRL decimals attribute (e.g., "-3", "2", "INF")
        scale_override: User override ("auto", "B", "M", "K")

    Returns:
        Scale suffix string (e.g., "K", "M", "$", "count")
    """
    # Handle scale override (not currently used in auto mode)
    if scale_override != "auto":
        return scale_override

    # Parse decimals to determine native scale
    if decimals is None:
        return "K"  # Default fallback for backward compatibility

    # Special cases
    if decimals == "INF":
        return "count"  # Share counts, pure numbers

    # Try to parse as integer
    try:
        dec_int = int(decimals)
    except (ValueError, TypeError):
        return ""  # Unknown format

    # Negative decimals indicate pre-scaled values
    if dec_int == -9:
        return "B"  # Billions
    elif dec_int == -6:
        return "M"  # Millions
    elif dec_int == -3:
        return "K"  # Thousands
    elif dec_int < 0:
        # Other negative decimals, use generic scale
        scale_factor = 10 ** (-dec_int)
        if scale_factor >= 1e9:
            return "B"
        elif scale_factor >= 1e6:
            return "M"
        elif scale_factor >= 1e3:
            return "K"
        else:
            return ""

    # Positive decimals = not scaled (per-share, ratios)
    elif dec_int >= 0:
        return "$"  # Dollar amounts per share, or pure ratios

    return ""  # Fallback
