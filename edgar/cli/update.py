import re
import sys
import sqlite3
from typing import Any, Iterable
from collections import defaultdict

# Local
from edgar import config
from edgar import db
from edgar import xbrl
from edgar.result import Result, ok, err, is_ok, is_not_ok
from edgar.cli.shared import Cmd


def add_arguments(subparsers):
    """Add update command to argument parser."""
    parser_update = subparsers.add_parser("update", help="extract facts from company filings")
    parser_update.add_argument("-t", "--ticker", nargs="+", help="company ticker symbols (if not specified, updates all)")
    parser_update.add_argument("-g", "--group", nargs="+", help="limit to specific groups (if not specified, updates all groups)")
    parser_update.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[None, str]:
    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    try:
        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result

        # Get filter for groups if specified
        group_filter = set(args.group) if args.group else None

        # Select entities from database (no external fetching)
        # If no tickers specified, get all tickers from database
        tickers = args.ticker if args.ticker else None
        result = db.queries.entities.select(conn, tickers)
        if is_not_ok(result):
            conn.close()
            return err(f"Error: {result[1]}")

        companies = result[1]
        if not companies:
            conn.close()
            if tickers:
                return err(f"update.run: no companies found for tickers {', '.join(tickers)}. Run 'probe filings' first.")
            else:
                return err("update.run: no companies found in database. Run 'probe filings' first.")

        # Print header
        print("TICKER  CIK         ACCESS_NO             DATE        PERIOD   CAND  CHOS  INS", file=sys.stderr)

        for company in companies:
            cik = company["cik"]
            ticker = company["ticker"].upper()

            # Get filings without facts (group-aware if group_filter is set)
            result = db.queries.filings.select_by_entity(conn, ciks=[cik], stubs_only=True, group_filter=group_filter)
            if is_not_ok(result):
                print(f"  Error querying filings: {result[1]}", file=sys.stderr)
                continue

            filings = result[1]
            if not filings:
                if group_filter:
                    groups_str = ", ".join(sorted(group_filter))
                    print(f"  up to date for groups: {groups_str}", file=sys.stderr)
                else:
                    print("  up to date (no filings without facts)", file=sys.stderr)
                continue

            for f in filings:
                access_no = f["access_no"]
                filing_date = f.get("filing_date", "?")

                # Get role mappings for this specific filing
                result = db.queries.role_patterns.match_groups_for_filing(conn, cik, access_no)
                if is_not_ok(result):
                    print(f"{ticker:<6}  {cik}  {access_no}  {filing_date}  ERROR: {result[1]}", file=sys.stderr)
                    continue

                role_map = result[1]
                if not role_map:
                    print(f"{ticker:<6}  {cik}  {access_no}  {filing_date}  ERROR: no groups with role patterns defined", file=sys.stderr)
                    continue

                # Filter by groups if specified
                if group_filter is not None:
                    role_map = {k: v for k, v in role_map.items() if k in group_filter}
                    if not role_map:
                        print(f"{ticker:<6}  {cik}  {access_no}  {filing_date}  ERROR: no matching groups found", file=sys.stderr)
                        continue

                result = _update_filing(conn, cik, access_no, role_map)

                # Print result row
                if is_ok(result):
                    stats = result[1]
                    print(f"{ticker:<6}  {cik}  {access_no}  {filing_date}  {stats['fiscal_period']:<7}  {stats['candidates']:4d}  {stats['chosen']:4d}  {stats['inserted']:4d}", file=sys.stderr)
                else:
                    # Print error row
                    print(f"{ticker:<6}  {cik}  {access_no}  {filing_date}  ERROR: {result[1]}", file=sys.stderr)

        conn.close()
        return ok(None)
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.update.run: {e}")


def _update_filing(conn: sqlite3.Connection, cik: str, access_no: str, role_map: dict[str, list[str]]) -> Result[dict[str, Any], str]:
    """
    Update facts for a single filing.
    Returns dict with stats: {fiscal_period, candidates, chosen, inserted}
    """
    # Get XBRL URL from database (should be cached by probe filings)
    result = db.queries.filings.get_xbrl_url(conn, access_no)
    if is_not_ok(result):
        return err(f"Error getting XBRL URL: {result[1]}")

    url = result[1]
    if not url:
        return err("no XBRL URL cached; run 'probe filings' first")

    # Load Arelle model
    result = xbrl.arelle.load_model(url)
    if is_not_ok(result):
        return err(f"failed to load Arelle model: {result[1]}")

    model = result[1]

    # Extract DEI
    dei = xbrl.arelle.extract_dei(model, access_no)

    # Update DEI in database
    result = db.queries.filings.insert_dei(conn, dei)
    if is_not_ok(result):
        return err(f"Error inserting DEI: {result[1]}")

    fiscal_period = dei.get("fiscal_period", "?")
    fiscal_year = dei.get("fiscal_year")
    if not fiscal_period or not fiscal_year:
        return err("missing DEI fiscal_period/year")

    all_candidates: list[dict[str, Any]] = []
    for group_name, role_tails in role_map.items():
        for role_tail in role_tails:
            facts = xbrl.arelle.extract_facts_by_role(model, role_tail)
            if not facts:
                continue
            consolidated_facts = [f for f in facts if xbrl.facts.is_consolidated(f)]
            records = _facts_to_records(conn, cik, consolidated_facts, access_no, role_tail)
            all_candidates.extend(records)

    if not all_candidates:
        return err("0 candidates found")

    doc_period_end = dei.get("doc_period_end")
    chosen = _choose_best_per_group(conn, cik, fiscal_year, fiscal_period, all_candidates, doc_period_end)

    # Insert facts
    result = db.queries.facts.insert(conn, chosen)
    if is_not_ok(result):
        return err(f"Error inserting facts: {result[1]}")

    inserted = result[1]

    return ok({
        "fiscal_period": f"{fiscal_period} {fiscal_year}",
        "candidates": len(all_candidates),
        "chosen": len(chosen),
        "inserted": inserted
    })


def _get_concept_name_from_patterns(conn: sqlite3.Connection, cik: str, tag: str) -> str | None:
    """
    Look up concept name from concept_patterns by matching tag against patterns.
    Returns the pattern name if found, None otherwise.
    """
    # Get all concept patterns for this CIK
    query = "SELECT name, pattern FROM concept_patterns WHERE cik = ?"
    result = db.store.select(conn, query, (cik,))
    if is_not_ok(result):
        return None

    patterns = result[1]

    # Match tag against each pattern
    for pattern_row in patterns:
        try:
            regex = re.compile(pattern_row["pattern"])
            if regex.search(tag):
                return pattern_row["name"]
        except re.error:
            continue  # Skip invalid patterns

    return None


def _facts_to_records(conn: sqlite3.Connection, cik: str, facts: Iterable[Any], access_no: str, role_tail: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for f in facts:
        taxonomy, tag = xbrl.facts.get_concept(f)

        # Lookup concept ID
        result = db.queries.concepts.get_id(conn, cik, taxonomy, tag)
        if is_not_ok(result):
            continue  # Skip this fact

        concept_id = result[1]
        if concept_id is None:
            # Insert new concept - use pattern name if available, otherwise fallback to tag
            name = _get_concept_name_from_patterns(conn, cik, tag)
            if name is None:
                # Fallback to filing label or tag
                name = getattr(getattr(f, "concept", None), "label", lambda: tag)()
            concept_data = [{"cik": cik, "taxonomy": taxonomy, "tag": tag, "name": name}]
            result = db.store.insert_or_ignore(conn, "concepts", concept_data)
            if is_not_ok(result):
                continue  # Skip this fact
            result = db.queries.concepts.get_id(conn, cik, taxonomy, tag)
            if is_not_ok(result):
                continue
            concept_id = result[1]

        rec = xbrl.facts.make_record(f, access_no, role_tail, concept_id)
        if rec and rec.get("value") is not None:
            out.append(rec)
    return out


def _choose_best_per_group(conn: sqlite3.Connection, cik: str, fiscal_year: str, fiscal_period: str, records: list[dict[str, Any]], doc_period_end: str | None = None) -> list[dict[str, Any]]:
    fact_groups: dict[tuple[int, bool, tuple[tuple[str, str], ...]], list[dict[str, Any]]] = defaultdict(list)

    for r in records:
        dims_items: tuple[tuple[str, str], ...] = tuple(sorted((r.get("dimensions") or {}).items()))
        key = (r["cid"], bool(dims_items), dims_items)
        fact_groups[key].append(r)

    chosen: list[dict[str, Any]] = []

    for (cid, has_dims, dims_items), items in fact_groups.items():
        dims_dict = dict(dims_items)

        # Get past fact modes for quarterly selection
        result = db.queries.facts.select_past_modes(conn, cik, fiscal_year, cid, dims_dict if has_dims else {})
        if is_not_ok(result):
            past_periods = []
        else:
            past_rows = result[1]
            past_periods: list[tuple[str, str]] = [(row["mode"], row["fiscal_period"]) for row in past_rows]

        # Check if this is a stock variable (all instant) or flow variable (has periods)
        # Stock variables (balance sheet): pick instant matching doc_period_end, or most recent
        # Flow variables (income/cash flow): use sophisticated QTD vs YTD selection logic
        if all(item.get("mode") == "instant" for item in items):
            # Stock variable: pick instant matching doc_period_end, or most recent
            best = None

            # Try to match doc_period_end exactly
            if doc_period_end:
                best = next((f for f in items if f["end_date"].isoformat() == doc_period_end), None)

            # Fallback: pick most recent instant (current period)
            if best is None:
                best = max(items, key=lambda f: f["end_date"], default=None)
        else:
            # Flow variable: use period-based selection
            match (fiscal_period.upper() if isinstance(fiscal_period, str) else fiscal_period):
                case "Q1":
                    best = xbrl.facts.get_best_q1(items)
                case "Q2":
                    best = xbrl.facts.get_best_q2(items, past_periods)
                case "Q3":
                    best = xbrl.facts.get_best_q3(items, past_periods)
                case _:
                    best = xbrl.facts.get_best_fy(items, past_periods)

        if best is not None:
            chosen.append(best)

    return chosen
