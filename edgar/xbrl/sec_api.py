import sys
import requests
from pathlib import Path
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# Local modules
from edgar import net
from edgar.result import Result, ok, err, is_ok, is_not_ok


USER_AGENT = "private_investor@mozmail.com"
URL_COMPANY_TICKERS = "https://www.sec.gov/files/company_tickers.json"
URL_SUBMISSIONS_BY_CIK = "https://data.sec.gov/submissions/{}.json"
URL_FILINGS_BY_CIK_ACCNO_URL = "https://www.sec.gov/Archives/edgar/data/{}/{}"


# Setup session with retries
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5)
session.mount("https://", HTTPAdapter(max_retries=retries))


def entity_fetch_by_tickers(tickers: list[str]) -> Result[list[dict], str]:
    """
    Fetch entity data from SEC API filtered by ticker symbols.
    """
    result = net.fetch_json(URL_COMPANY_TICKERS, USER_AGENT)
    if is_not_ok(result):
        return result
    
    data = result[1]
    selected = set(ticker.upper() for ticker in tickers)
    entities = []
    
    for entity in data.values():
        if not all(key in entity for key in ["ticker", "cik_str", "title"]):
            continue
            
        if entity["ticker"].upper() in selected:
            entities.append({
                "cik": f"{int(entity['cik_str']):010d}",
                "ticker": entity["ticker"].lower(),
                "name": entity["title"]
            })
    
    return ok(entities)


def filing_url(cik: str, accno: str) -> str:
    """
    Build SEC filing URL from CIK and accession number.
    """
    return URL_FILINGS_BY_CIK_ACCNO_URL.format(cik, str(accno).replace("-", ""))


def filing_fetch_index(cik: str, accno: str) -> Result[list[str], str]:
    """
    Fetch list of files in a SEC filing directory.
    """
    url = filing_url(cik, accno) + "/index.json"
    
    result = net.fetch_json(url, USER_AGENT)
    if is_not_ok(result):
        return result
    
    data = result[1]
    directory = data.get("directory", {})
    items = directory.get("item", [])
    
    filenames = []
    for item in items:
        if isinstance(item, dict) and "name" in item:
            filenames.append(item["name"])
    
    return ok(filenames)


def filing_fetch_xbrl_url(cik: str, accno: str) -> Result[str | None, str]:
    """
    Find XBRL file URL in a SEC filing by checking file contents.
    Returns the URL if found, None if no XBRL content found.
    """
    result = filing_fetch_index(cik, accno)
    if is_not_ok(result):
        return result
    
    files = result[1]
    
    # Prefer .xml files, then .htm/.html
    preferred = sorted(
        [f for f in files if f.endswith((".xml", ".htm", ".html"))],
        key=lambda x: 0 if x.endswith(".xml") else 1
    )
    
    # Check each file for XBRL content
    for filename in preferred:
        file_url = filing_url(cik, accno) + "/" + filename
        
        result = net.check_content(file_url, ["<xbrl", "<ix:"], USER_AGENT)
        if is_not_ok(result):
            continue
        
        if result[1]:
            return ok(file_url)
    
    return ok(None)


def filing_fetch_by_cik(cik: str, form_types: set[str]) -> Result[list[dict], str]:
    """
    Fetch all filings for a company from SEC API, filtered by form types.
    """
    
    url = URL_SUBMISSIONS_BY_CIK.format(f"CIK{cik}")
    
    result = net.fetch_json(url, USER_AGENT)
    if is_not_ok(result):
        return result
    
    data = result[1]
    recent = data.get("filings", {}).get("recent", {})
    
    # Map SEC field names to our field names
    field_mapping = {
        "access_no": "accessionNumber", 
        "form_type": "form", 
        "primary_doc": "primaryDocument",
        "filing_date": "filingDate", 
        "is_xbrl": "isXBRL", 
        "is_ixbrl": "isInlineXBRL"
    }
    
    filings = []
    for row in zip(*(recent.get(field_mapping[k], []) for k in field_mapping)):
        item = {"cik": cik}
        item.update(dict(zip(field_mapping.keys(), row)))
        
        if item["form_type"] in form_types:
            item["is_amendment"] = item["form_type"].endswith("/A")
            filings.append(item)
    
    return ok(filings)
