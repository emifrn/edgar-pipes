"""
pipeline.py - Pipeline orchestration and packet envelope management
"""

import sys
import json
import shlex
from typing import Any, TypedDict

# Local modules
from edgar import result
from edgar.result import Result
from edgar.cli.shared import Cmd


class Packet(TypedDict):
    cmd: Cmd
    pipeline: list[str]


def output_format() -> str:
    """
    Smart format detection based on terminal context.
    
    Returns:
        'table' if outputting to terminal (human-readable)
        'packet' if outputting to pipe/file (machine-readable JSON envelope)
    """
    if sys.stdout.isatty():
        return 'table'
    else:
        return 'packet'


def ok(cmd_name: str, data: list[dict]) -> str:
    """Create successful packet record in JSON envelope format."""
    return json.dumps({"ok": True, "name": cmd_name, "data": data})


def err(message: str) -> str:
    """Create error packet record in JSON envelope format."""
    return json.dumps({"ok": False, "name": "error", "data": message})


def read() -> Result[tuple[Packet | None, dict], str]:
    """
    Read single packet from stdin and extract packet and context.

    Returns:
        Ok((Packet, context)) - Successfully parsed packet with cmd, pipeline, and context
        Ok((None, {})) - No piped input (terminal start) or empty input
        Err(str) - Error packet received or parsing failure

    Behavior:
        - Returns (None, {}) if no piped input (start of pipeline)
        - Stops on first error packet and returns the error message
        - Extracts command data, pipeline history, and context
        - Validates JSON structure
    """
    if sys.stdin.isatty():
        return result.ok((None, {}))  # No piped input - start of pipeline

    # Read first non-empty line as single packet
    line = sys.stdin.readline().strip()

    if not line:
        return result.ok((None, {}))  # Empty input

    try:
        envelope = json.loads(line)
    except json.JSONDecodeError as e:
        return result.err(f"pipeline.read: invalid JSON - {e}")

    # Validate envelope structure
    if not isinstance(envelope, dict):
        return result.err(f"pipeline.read: expected JSON object, got {type(envelope).__name__}")

    if "ok" not in envelope:
        return result.err(f"pipeline.read: missing 'ok' field in packet")

    # Check for error
    if not envelope["ok"]:
        error_msg = envelope.get("data", "unknown packet error")
        return result.err(str(error_msg))

    # Extract command data from success packet
    if "data" not in envelope or "name" not in envelope:
        return result.err(f"pipeline.read: missing required fields in packet")

    cmd = {
        "name": envelope["name"],
        "data": envelope["data"]
    }

    # Extract context
    context = envelope.get("context", {})

    # Extract pipeline from context
    pipeline = context.get("pipeline", [])

    packet = {
        "cmd": cmd,
        "pipeline": pipeline
    }

    return result.ok((packet, context))


def build_current_command() -> str:
    """Build properly quoted command string from sys.argv."""
    return ' '.join(shlex.quote(arg) for arg in sys.argv[1:])


def write(packet: Packet, context: dict) -> None:
    """Write packet to stdout in JSON envelope format with context."""
    # Build context with pipeline history
    context_out = dict(context)
    context_out["pipeline"] = packet["pipeline"]

    envelope = {
        "ok": True,
        "name": packet["cmd"]["name"],
        "data": packet["cmd"]["data"],
        "context": context_out
    }
    print(json.dumps(envelope))


def add(packet: Packet | None, current_command: str) -> Packet:
    """Add current command to pipeline history."""
    if packet is None:
        # Start of pipeline
        return {
            "cmd": {"name": "", "data": []},  # Empty cmd, will be filled by command
            "pipeline": [current_command]
        }
    else:
        # Continue existing pipeline
        return {
            "cmd": packet["cmd"],
            "pipeline": packet["pipeline"] + [current_command]
        }
