def _mode_from_days(days: int) -> str:
    """Private helper: classify period mode based on duration in days."""
    if days == 1:
        return "instant"
    elif 88 <= days <= 95:
        return "quarter"
    elif 170 <= days <= 185:
        return "semester"
    elif 260 <= days <= 275:
        return "threeQ"
    elif 350 <= days <= 373:
        return "year"
    else:
        return "period"


def get_concept(fact) -> tuple[str, str]:
    """
    Extract taxonomy URI and tag from XBRL fact.
    Returns (taxonomy_uri, tag).
    """
    taxonomy_uri = fact.qname.namespaceURI
    tag = fact.qname.localName
    return taxonomy_uri, tag


def taxonomy_name(taxonomy_uri: str) -> str:
    """
    Extract taxonomy name with version from URI.
    Examples:
      http://fasb.org/us-gaap/2025 → us-gaap/2025
      http://xbrl.sec.gov/dei/2023 → dei/2023
    """
    uri_parts = taxonomy_uri.rstrip('/').split('/')
    if len(uri_parts) >= 2:
        # Return last two parts: "us-gaap/2025" instead of just "us-gaap"
        return "/".join(uri_parts[-2:])
    return taxonomy_uri  # Fallback to full URI if parsing fails


def make_record(fact, access_no: str, role: str, concept_id: int) -> dict:
    """
    Convert XBRL fact to database record format.
    """
    ctx = fact.context
    if ctx is None:
        return {}

    if ctx.isInstantPeriod:
        start = end = ctx.instantDatetime
        mode = "instant"
    elif ctx.isStartEndPeriod:
        start = ctx.startDatetime
        end = ctx.endDatetime
        mode = _mode_from_days((end - start).days + 1)
    else:
        return {}

    try:
        unit = fact.unit.measures[0][0].localName if fact.unit is not None else None
    except Exception:
        unit = None

    # Extract decimals attribute for scale information
    try:
        decimals = str(fact.decimals) if fact.decimals is not None else None
    except Exception:
        decimals = None

    dimensions = {
        dim.dimensionQname.localName: dim.memberQname.localName
        for dim in getattr(ctx, 'dims', {}).values()
    }

    try:
        value = float(fact.value)
    except Exception:
        value = None

    return {
        "access_no": access_no,
        "role": role,
        "cid": concept_id,
        "value": value,
        "start_date": start.date(),
        "end_date": end.date(),
        "mode": mode,
        "unit": unit,
        "decimals": decimals,
        "dimensions": dimensions,
        "has_dimensions": bool(dimensions),
    }


def is_consolidated(fact) -> bool:
    """
    Check if fact represents consolidated data (no segments or dimensions).
    """
    ctx = fact.context
    if ctx is None:
        return False
    dims = getattr(ctx, "dims", None)
    return not getattr(ctx, "hasSegment", False) and (dims is None or len(dims) == 0)


def _date_distance(end_date, doc_period_end_str):
    """
    Calculate absolute difference between fact end_date and doc_period_end string.
    Returns difference in days as integer for sorting.
    """
    from datetime import datetime, date

    # Convert end_date to ISO string for comparison
    if hasattr(end_date, 'isoformat'):
        end_date_str = end_date.isoformat()
    else:
        end_date_str = str(end_date)

    # Parse both as dates for proper comparison
    try:
        end_dt = datetime.fromisoformat(end_date_str).date() if isinstance(end_date_str, str) else end_date
        doc_dt = datetime.fromisoformat(doc_period_end_str).date()
        return abs((end_dt - doc_dt).days)
    except:
        # Fallback to string comparison if parsing fails
        return 0 if end_date_str == doc_period_end_str else 999999


def get_best_q1(facts, past_periods=None, doc_period_end=None) -> dict | None:
    """
    Get best Q1 fact from collection.
    Prefers facts with end_date closest to doc_period_end if provided.
    """
    candidates = [f for f in facts if f["mode"] == "quarter"]
    if not candidates:
        return None

    # If doc_period_end provided, prefer fact with closest end_date
    if doc_period_end:
        return min(candidates, key=lambda f: _date_distance(f["end_date"], doc_period_end))

    return candidates[0]


def get_best_q2(facts, past_periods=None, doc_period_end=None) -> dict | None:
    """
    Get best Q2 fact from collection, considering past periods.
    Prefers quarter-mode facts over semester (6M YTD) when available.
    Falls back to semester only if no quarter fact exists.
    Prefers facts with end_date closest to doc_period_end if provided.
    """
    past_periods = past_periods or []
    has_q1 = any(p == "Q1" for _, p in past_periods)

    # Look for direct quarter facts first
    quarter_candidates = [f for f in facts if f["mode"] == "quarter"]
    semester_candidates = [f for f in facts if f["mode"] == "semester"]

    # Prefer quarter mode if available (direct Q2 reporting)
    if quarter_candidates:
        if doc_period_end:
            return min(quarter_candidates, key=lambda f: _date_distance(f["end_date"], doc_period_end))
        return quarter_candidates[0]

    # Fall back to semester (6M YTD) only if we have Q1 and no quarter fact
    if semester_candidates and has_q1:
        if doc_period_end:
            return min(semester_candidates, key=lambda f: _date_distance(f["end_date"], doc_period_end))
        return semester_candidates[0]

    # No suitable facts found
    return None


def get_best_q3(facts, past_periods=None, doc_period_end=None) -> dict | None:
    """
    Get best Q3 fact from collection, considering past periods.
    Prefers facts with end_date closest to doc_period_end if provided.
    """
    past_periods = past_periods or []
    past = {(m, p) for m, p in past_periods}
    options = [f for f in facts if f["mode"] in ("threeQ", "quarter")]

    if not options:
        return None

    # If doc_period_end provided, filter options to those closest to it first
    if doc_period_end:
        # Group by mode, then pick closest within each mode
        threeQ_options = [f for f in options if f["mode"] == "threeQ"]
        quarter_options = [f for f in options if f["mode"] == "quarter"]

        # Pick best threeQ if available and applicable
        if threeQ_options and (("semester", "Q2") in past or (("quarter", "Q1") in past and ("quarter", "Q2") in past)):
            return min(threeQ_options, key=lambda f: _date_distance(f["end_date"], doc_period_end))

        # Otherwise pick best quarter
        if quarter_options:
            return min(quarter_options, key=lambda f: _date_distance(f["end_date"], doc_period_end))

        # Fallback to any option
        return min(options, key=lambda f: _date_distance(f["end_date"], doc_period_end))

    # Original logic without doc_period_end
    def rank(f):
        if f["mode"] == "threeQ":
            if ("semester", "Q2") in past or (("quarter", "Q1") in past and ("quarter", "Q2") in past):
                return 0
        if f["mode"] == "quarter":
            return 1
        return 99

    return min(options, key=rank, default=None)


def get_best_fy(facts, past_periods) -> dict | None:
    """
    Get best full-year fact from collection.
    """
    options = [f for f in facts if f.get("mode") in ("year", "quarter", "period")]
    rank = {"year": 0, "quarter": 1, "period": 2}
    return min(options, key=lambda f: rank.get(f["mode"], 99), default=None)
