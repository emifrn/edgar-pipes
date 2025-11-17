"""
CLI: format termination commands and formatting functions

Termination commands that read pipeline envelope format and output in specific formats.
All errors go to stderr, successful data goes to stdout in target format.

Also contains shared formatting functions used by main.py for smart format detection.
"""

import io
import sys
import csv
import json
from typing import Any

# Local modules
from edgar import cli
from edgar import cli
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_not_ok


# =============================================================================
# FORMATTING FUNCTIONS
# =============================================================================

def as_csv(data: list[dict]) -> str:
    """Format data as CSV string."""
    if not data:
        return ""

    # Generate CSV string
    if data:
        output = io.StringIO()
        # Collect all unique field names across all records (handles sparse data)
        headers = []
        seen = set()
        for record in data:
            for key in record.keys():
                if key not in seen:
                    headers.append(key)
                    seen.add(key)
        writer = csv.DictWriter(output, fieldnames=headers, lineterminator='\n')
        writer.writeheader()
        writer.writerows(data)
        return output.getvalue().rstrip()  # Remove trailing newline
    return ""


def as_json(data: list[dict]) -> str:
    """Format data as JSONL string (one object per line)."""
    lines = []
    for item in data:
        lines.append(json.dumps(item))
    return '\n'.join(lines)


def as_tsv(data: list[dict]) -> str:
    """Format data as gnuplot-friendly TSV with comment header."""
    if not data:
        return ""

    # Collect all unique field names across all records (handles sparse data)
    headers = []
    seen = set()
    for record in data:
        for key in record.keys():
            if key not in seen:
                headers.append(key)
                seen.add(key)

    # Build output lines
    lines = []

    # Add header line
    lines.append("\t".join(headers))

    # Add data rows
    for record in data:
        row = []
        for header in headers:
            value = record.get(header, "")
            row.append(str(value) if value is not None else "")
        lines.append("\t".join(row))

    return '\n'.join(lines)


def as_table(data: list[dict], theme_name: str = None) -> str:
    """Format data as Rich-themed table string."""
    if not data:
        return ""

    # Get theme name from parameter or environment
    if theme_name is None:
        theme_name = cli.themes.get_default_theme()

    # All data is flat - use Rich themed output
    return cli.themes.themed_table(data, headers=None, theme_name=theme_name)


def as_packets(packet_type: str, data: list[dict]) -> str:
    """Format data as packet envelope strings."""
    lines = []
    for item in data:
        lines.append(cli.shared.packet_ok(packet_type, item))
    return '\n'.join(lines)
