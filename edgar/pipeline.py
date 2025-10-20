"""
pipeline.py - Pipeline orchestration and packet envelope management
"""

import sys
import json
import shlex
from typing import Any, TypedDict

# Local modules
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err


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


def packet_ok(cmd_name: str, data: list[dict]) -> str:
    """Create successful packet record in JSON envelope format."""
    return json.dumps({"ok": True, "name": cmd_name, "data": data})


def packet_err(message: str) -> str:
    """Create error packet record in JSON envelope format."""
    return json.dumps({"ok": False, "name": "error", "data": message})


def packet_read() -> Result[Packet | None, str]:
    """
    Read packet format from stdin and convert to internal Packet format.
    
    Returns:
        Ok(Packet) - Successfully parsed packet with cmd and pipeline info
        Ok(None) - No piped input (terminal start)
        Err(str) - First error encountered or parsing failure
        
    Behavior:
        - Returns None if no piped input (start of pipeline)
        - Stops on first error packet and returns the error message
        - Extracts command data and attempts to rebuild pipeline history
        - Validates JSON structure
    """
    if sys.stdin.isatty():
        return ok(None)  # No piped input - start of pipeline
    
    # For now, read single packet from stdin
    # TODO: Handle multiple packets if needed
    for line_no, line in enumerate(sys.stdin, 1):
        line = line.strip()
        if not line:
            continue
            
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError as e:
            return err(f"pipeline.packet_read: line {line_no}: invalid JSON - {e}")
        
        # Validate envelope structure
        if not isinstance(envelope, dict):
            return err(f"pipeline.packet_read: line {line_no}: expected JSON object, got {type(envelope).__name__}")
        
        if "ok" not in envelope:
            return err(f"pipeline.packet_read: line {line_no}: missing 'ok' field in packet")
        
        # Check for error
        if not envelope["ok"]:
            error_msg = envelope.get("data", "unknown packet error")
            return err(str(error_msg))
        
        # Extract command data from success packet
        if "data" not in envelope or "name" not in envelope:
            return err(f"pipeline.packet_read: line {line_no}: missing required fields in packet")
        
        cmd = {
            "name": envelope["name"],
            "data": envelope["data"]
        }
        
        # Extract pipeline history if available, otherwise start fresh
        pipeline = envelope.get("pipeline", [])
        
        packet = {
            "cmd": cmd,
            "pipeline": pipeline
        }
        
        return ok(packet)
    
    return ok(None)  # Empty input


def build_current_command() -> str:
    """Build properly quoted command string from sys.argv."""
    return ' '.join(shlex.quote(arg) for arg in sys.argv[1:])


def packet_write(packet: Packet) -> None:
    """Write packet to stdout in JSON envelope format."""
    envelope = {
        "ok": True,
        "name": packet["cmd"]["name"],
        "data": packet["cmd"]["data"],
        "pipeline": packet["pipeline"]
    }
    print(json.dumps(envelope))


def add_to_pipeline(packet: Packet | None, current_command: str) -> Packet:
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
