import requests
from typing import Any
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# Local modules
from edgar.result import Result, ok, err, is_not_ok

# Setup session with retries
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5)
session.mount("https://", HTTPAdapter(max_retries=retries))


def fetch_json(url: str, user_agent: str, timeout: int = 30) -> Result[Any, str]:
    """
    Fetch and parse JSON from URL.
    """
    try:
        response = session.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
        response.raise_for_status()
        return ok(response.json())
    except requests.exceptions.Timeout:
        return err(f"net.fetch_json() timeout after {timeout}s")
    except requests.exceptions.ConnectionError:
        return err(f"net.fetch_json() connection failed")
    except requests.exceptions.HTTPError as e:
        return err(f"net.fetch_json() HTTP {e.response.status_code}")
    except requests.exceptions.RequestException as e:
        return err(f"net.fetch_json() request failed: {e}")
    except ValueError as e:
        return err(f"net.fetch_json() JSON parse failed: {e}")


def fetch_text(url: str, user_agent: str, timeout: int = 30) -> Result[str, str]:
    """
    Fetch raw text content from URL.
    """
    try:
        response = session.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
        response.raise_for_status()
        return ok(response.text)
    except requests.exceptions.Timeout:
        return err(f"net.fetch_text() timeout after {timeout}s")
    except requests.exceptions.ConnectionError:
        return err(f"net.fetch_text() connection failed")
    except requests.exceptions.HTTPError as e:
        return err(f"net.fetch_text() HTTP {e.response.status_code}")
    except requests.exceptions.RequestException as e:
        return err(f"net.fetch_text() request failed: {e}")


def check_content(url: str, patterns: list[str], user_agent: str, timeout: int = 30) -> Result[bool, str]:
    """
    Check if URL content contains any of the specified patterns.
    Returns True if any pattern is found, False if none are found.
    """
    result = fetch_text(url, user_agent, timeout)
    if is_not_ok(result):
        return result
    
    content = result[1]
    found = any(pattern in content for pattern in patterns)
    return ok(found)
