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

def _pivot_to_long(group_record: dict) -> list[dict]:
    """
    Convert one group record to multiple flat records.
    """
    group_fields, array_fields = cli.shared.separate_group_and_array_fields(group_record)
    
    if not array_fields:
        return [group_fields]  # No arrays, return as-is
    
    # Validate array lengths are consistent
    array_lengths = [len(values) for values in array_fields.values()]
    if array_lengths and not all(length == array_lengths[0] for length in array_lengths):
        # This should not happen in well-formed grouped data, but handle gracefully
        max_length = max(array_lengths)
    else:
        max_length = array_lengths[0] if array_lengths else 0
    
    # Create one flat record per array index
    flat_records = []
    for i in range(max_length):
        record = dict(group_fields)  # Start with group keys
        for field_name, values in array_fields.items():
            record[field_name] = values[i] if i < len(values) else None
        flat_records.append(record)
    
    return flat_records


def as_csv(data: list[dict]) -> str:
    """Format data as CSV string."""
    if not data:
        return ""

    # Handle grouped data by flattening to individual records
    if cli.shared.is_grouped_data(data):
        flat_records = []
        for record in data:
            flat_records.extend(_pivot_to_long(record))
        data = flat_records

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
        writer = csv.DictWriter(output, fieldnames=headers)
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


def as_table(data: list[dict], theme_name: str = None) -> str:
    """Format data as Rich-themed table string."""
    if not data:
        return ""
    
    # Get theme name from parameter or environment
    if theme_name is None:
        theme_name = cli.themes.get_default_theme()
    
    if cli.shared.is_grouped_data(data):
        # Output one table section per group using Rich theming
        sections = []
        for group_record in data:
            group_fields, array_fields = cli.shared.separate_group_and_array_fields(group_record)
            
            section_lines = []
            
            # Group header - use Rich markup for styling
            if group_fields:
                group_parts = [f"{field}={value}" for field, value in group_fields.items()]
                header_text = f"=== {' | '.join(group_parts)} ==="
                # Add Rich styling to group headers
                if cli.themes.should_use_color():
                    header_text = f"[bold cyan]{header_text}[/bold cyan]"
                section_lines.append(header_text)
            
            # Convert arrays to flat records for this group
            if array_fields:
                flat_records = _pivot_to_long(group_record)
                if flat_records and array_fields:
                    # Use Rich themed table for array data
                    array_headers = list(array_fields.keys())
                    themed_output = cli.themes.themed_table(flat_records, array_headers, theme_name)
                    section_lines.append(themed_output)
            
            sections.append('\n'.join(section_lines))
        
        return '\n\n'.join(sections)
    else:
        # Regular flat data table - use Rich themed output
        return cli.themes.themed_table(data, headers=None, theme_name=theme_name)


def as_packets(packet_type: str, data: list[dict]) -> str:
    """Format data as packet envelope strings."""
    lines = []
    for item in data:
        lines.append(cli.shared.packet_ok(packet_type, item))
    return '\n'.join(lines)
