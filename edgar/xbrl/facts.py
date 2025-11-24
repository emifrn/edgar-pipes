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


def get_best_q1(facts) -> dict | None:
    """
    Get best Q1 fact from collection.
    """
    return next((f for f in facts if f["mode"] == "quarter"), None)


def get_best_q2(facts, past_periods) -> dict | None:
    """
    Get best Q2 fact from collection, considering past periods.
    """
    has_q1 = any(p == "Q1" for _, p in past_periods)
    preferred = [f for f in facts if f["mode"] == "semester"]
    if preferred and has_q1:
        return preferred[0]
    return next((f for f in facts if f["mode"] == "quarter"), None)


def get_best_q3(facts, past_periods) -> dict | None:
    """
    Get best Q3 fact from collection, considering past periods.
    """
    past = {(m, p) for m, p in past_periods}
    options = [f for f in facts if f["mode"] in ("threeQ", "quarter")]

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
