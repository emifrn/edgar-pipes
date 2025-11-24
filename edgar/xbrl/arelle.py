import os
import sys
from arelle import Cntlr
from arelle.ModelXbrl import ModelXbrl
from datetime import datetime, timedelta

# Local
from edgar import xbrl
from edgar.result import Result, ok, err


PRESENTATION_ARCROLE = "http://www.xbrl.org/2003/arcrole/parent-child"


def load_model(file_url: str) -> Result[ModelXbrl, str]:
    """
    Load XBRL model from URL using Arelle library.
    """
    try:
        cntlr = Cntlr.Cntlr(logFileName=os.devnull)
        model = cntlr.modelManager.load(file_url)
        
        if model is None:
            return err(f"load_model() failed to load XBRL from {file_url}")
        
        return ok(model)
        
    except Exception as e:
        return err(f"load_model() {type(e).__name__}: {e}")


def _get_role_uri(model: ModelXbrl, tail: str) -> str | None:
    """
    Find full role URI by matching the tail portion.
    Returns the full URI if found, None if not found.
    """
    for roleType in model.roleTypes:
        uri_tail = roleType.rsplit("/", 1)[-1]
        if uri_tail.lower() == tail.lower():
            return roleType
    return None


def extract_roles(model: ModelXbrl) -> list[str]:
    """Extract all role tails (linkrole URIs stripped of prefix) from the model."""

    return [uri.rsplit("/", 1)[-1] for uri in model.roleTypes]


def extract_facts_by_role(model: ModelXbrl, role_tail: str) -> list:
    """
    Extract all facts for a specific role from the XBRL model.
    """
    role_uri = _get_role_uri(model, role_tail)
    if not role_uri:
        return []

    rs = model.relationshipSet(PRESENTATION_ARCROLE, linkrole=role_uri)
    if not rs:
        return []

    out = []
    seen = set()

    for root in rs.rootConcepts:
        stack = [root]
        while stack:
            concept = stack.pop()
            if concept.qname in seen:
                continue
            seen.add(concept.qname)
            out.extend(model.factsByQname.get(concept.qname, []))
            for rel in rs.fromModelObject(concept):
                stack.append(rel.toModelObject)

    return out


def extract_concepts_by_role(model: ModelXbrl, role: str) -> list[dict[str, str]]:
    """
    Extract unique concept definitions for a specific role.
    """
    facts = extract_facts_by_role(model, role)
    seen = set()
    out = []

    for f in facts:
        key = (f.qname.namespaceURI, f.qname.localName)
        if key not in seen:
            seen.add(key)
            taxonomy, tag = xbrl.facts.get_concept(f)
            out.append({
                "taxonomy": taxonomy,
                "tag": tag,
                "name": f.concept.label(),
                "balance": f.concept.balance,  # Extract balance attribute (debit/credit/None)
            })

    return out


def extract_dei(model: ModelXbrl, access_no: str) -> dict[str, str]:
    """
    Extract Document Entity Information from XBRL model.
    Returns available DEI data, handling malformed dates gracefully.
    """
    def to_month_day(s: str) -> str | None:
        try:
            s = s.lstrip("-")
            return datetime.strptime(s, "%m-%d").strftime("%m-%d")
        except Exception:
            return None

    fields = {
        "DocumentType": "doc_type",
        "DocumentPeriodEndDate": "doc_period_end",
        "DocumentFiscalPeriodFocus": "fiscal_period",
        "DocumentFiscalYearFocus": "fiscal_year",
        "CurrentFiscalYearEndDate": "fiscal_month_day_end",
        "EntityReportingCalendarYearStartDate": "fiscal_month_day_start"
    }

    dei = {"access_no": access_no}

    for fact in model.facts:
        if fact.qname.localName in fields and "dei" in fact.qname.namespaceURI:
            dei[fields[fact.qname.localName]] = fact.value

    # Validate doc_period_end date format
    try:
        datetime.strptime(dei.get("doc_period_end"), "%Y-%m-%d")
    except (ValueError, TypeError):
        dei.pop("doc_period_end", None)

    # Normalize fiscal dates
    if "fiscal_month_day_end" in dei:
        if s := to_month_day(dei["fiscal_month_day_end"]):
            dei["fiscal_month_day_end"] = s

    if "fiscal_month_day_start" in dei:
        if s := to_month_day(dei["fiscal_month_day_start"]):
            dei["fiscal_month_day_start"] = s

    # Calculate missing fiscal dates
    if "fiscal_month_day_end" in dei and "fiscal_month_day_start" not in dei:
        mm, dd = map(int, dei["fiscal_month_day_end"].split("-"))
        end_date = datetime(2000, mm, dd)
        start_date = end_date + timedelta(days=1)
        dei["fiscal_month_day_start"] = start_date.strftime("%m-%d")

    if "fiscal_month_day_start" in dei and "fiscal_month_day_end" not in dei:
        mm, dd = map(int, dei["fiscal_month_day_start"].split("-"))
        start_date = datetime(2000, mm, dd)
        end_date = start_date - timedelta(days=1)
        dei["fiscal_month_day_end"] = end_date.strftime("%m-%d")

    return dei
