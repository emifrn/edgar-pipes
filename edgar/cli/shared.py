"""
cli/shared.py - Shared validators and constants for CLI modules
"""

import re
import sys
import csv
import json
import argparse
import datetime
from typing import Any, TypedDict

from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn


class Cmd(TypedDict):
    name: str
    data: list[dict[str, Any]]


# Local modules
from edgar.result import Result, ok, err, is_ok, is_not_ok


PROBE_FORMS = ["10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "40-F"]


def check_date(date: str):
    """
    Parse and validate date in YYYY-MM-DD format.
    """
    try:
        return datetime.datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Not a valid date: '{date}'. Expected format: YYYY-MM-DD")


def parse_date_constraints(date_args: list[str] | None, field_name: str = 'filing_date') -> list[tuple[str, str, str]] | None:
    """
    Parse date filter arguments into database filter tuples.

    Args:
        date_args: List of date constraints like ['>2024-01-01', '<=2024-12-31']
        field_name: Database field to filter on (default: 'filing_date')

    Returns:
        List of (field, operator, value) tuples, or None if no constraints

    Examples:
        parse_date_constraints(['>2024-01-01'])
        → [('filing_date', '>', '2024-01-01')]

        parse_date_constraints(['>=2023-01-01', '<2024-01-01'])
        → [('filing_date', '>=', '2023-01-01'), ('filing_date', '<', '2024-01-01')]
    """
    if not date_args:
        return None

    date_filters = []
    for date_str in date_args:
        match = re.match(r'^\s*([><=!]+)(.+)$', date_str.strip())
        if match:
            operator = match.group(1)
            value = match.group(2).strip()
            # Normalize != to <> for SQL
            if operator == '!=':
                operator = '<>'
        else:
            # No operator means equality
            operator = '='
            value = date_str.strip()

        # Validate date format
        try:
            datetime.datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid date format: '{value}'. Expected YYYY-MM-DD")

        date_filters.append((field_name, operator, value))

    return date_filters


def _cols_grep(available_cols: list[str], desired_cols: list[str]) -> Result[list[str], str]:
    """
    Filter available columns to only those that exist in desired list.
    Like grep - find matches between two lists.
    """
    valid_cols = [col for col in desired_cols if col in available_cols]
    
    if not valid_cols:
        return err(f"cli.shared._cols_grep: none of the requested columns are available")
    
    return ok(valid_cols)


def _cols_parse(cols_args: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """
    Parse column specifications with embedded sort directions.
    
    Args:
        cols_args: List like ['role_name+', 'access_no', 'filing_date-']
    
    Returns:
        Tuple of (display_columns, sort_specifications)
        where sort_specifications is [(column, 'ASC'|'DESC'), ...]
    """
    display_cols = []
    sort_specs = []
    
    for col_spec in cols_args:
        if col_spec.endswith('+'):
            col_name = col_spec[:-1]
            sort_specs.append((col_name, 'ASC'))
        elif col_spec.endswith('-'):
            col_name = col_spec[:-1]
            sort_specs.append((col_name, 'DESC'))
        else:
            col_name = col_spec
            
        display_cols.append(col_name)
    
    return display_cols, sort_specs


def _cols_reverse(value):
    """
    Helper to reverse sort order for descending sorts.
    """
    if isinstance(value, str):
        # For strings, use tuple of negated ord values to reverse lexicographic order
        return tuple(-ord(c) for c in value)
    elif isinstance(value, (int, float)):
        return -value
    else:
        # For other types, convert to string and reverse
        return tuple(-ord(c) for c in str(value))


def _cols_make_sort(sort_specs):
    """
    Create sort key function from sort specifications for scalar fields only.
    """
    def sort_key(row):
        return tuple(
            row.get(col, '') 
            if direction == 'ASC' 
            else _cols_reverse(row.get(col, ''))
            for col, direction in sort_specs
            if not isinstance(row.get(col), list)  # Only scalar fields
        )
    return sort_key


def process_cols(data: list[dict],
                 cols_args: list[str] | None,
                 default_cols: list[str]) -> Result[tuple[list[dict], list[str]], str]:
    """
    Apply column processing: parsing, validation, sorting (type-aware), filtering.
    Returns (processed_data, column_headers).

    Note: Always preserves 'pid' field in data for delete command compatibility,
    even if not in display columns.
    """
    if not data:
        return ok(([], []))

    # Determine columns and sort specs
    if cols_args:
        display_cols, sort_specs = _cols_parse(cols_args)
    else:
        display_cols = default_cols
        sort_specs = []

    # Validate columns
    available_cols = list(data[0].keys())
    result = _cols_grep(available_cols, display_cols)
    if is_not_ok(result):
        return result

    valid_cols = result[1]

    # Apply type-aware sorting if specified
    processed_data = data
    if sort_specs:
        try:
            # Step 1: Sort arrays within each record independently
            processed_data = []
            for record in data:
                processed_record = dict(record)  # Copy the record

                for col, direction in sort_specs:
                    if col in processed_record and isinstance(processed_record[col], list):
                        # Sort array field in-place
                        reverse = (direction == 'DESC')
                        processed_record[col] = sorted(processed_record[col], reverse=reverse)

                processed_data.append(processed_record)

            # Step 2: Sort records by scalar fields (cross-record sorting)
            scalar_sort_specs = [(col, direction) for col, direction in sort_specs
                                 if not isinstance(processed_data[0].get(col), list)]

            if scalar_sort_specs:
                processed_data = sorted(processed_data, key=_cols_make_sort(scalar_sort_specs))

        except Exception as e:
            return err(f"shared.process_cols: sorting failed: {e}")

    # Filter data to selected columns, but always preserve 'pid' and 'gid' for pipeline compatibility
    filtered_data = []
    for row in processed_data:
        filtered_row = {col: row[col] for col in valid_cols}
        # Preserve pid if it exists (needed for delete command)
        if 'pid' in row and 'pid' not in filtered_row:
            filtered_row['pid'] = row['pid']
        # Preserve gid if it exists (needed for modify group pipeline)
        if 'gid' in row and 'gid' not in filtered_row:
            filtered_row['gid'] = row['gid']
        filtered_data.append(filtered_row)

    return ok((filtered_data, valid_cols))


def merge_stdin_field(field_name: str,
                      stdin_data: list[dict],
                      explicit_values: list[str] | None = None) -> list[str] | None:
    """
    Extract scalar field from stdin packets and merge with explicit values.

    Returns None if no values found, list of values otherwise.
    """
    merged_values = []

    # Extract from stdin
    for item in stdin_data:
        if field_name in item:
            merged_values.append(item[field_name])

    # Add explicit values
    if explicit_values:
        merged_values.extend(explicit_values)

    return merged_values if merged_values else None


def strip_units(col_name: str) -> str:
    """
    Strip unit suffix from column name.

    Used by pipeline commands that need to match column names with or without
    unit suffixes added by the report command's scaling (e.g., "(K)", "($)", "(count)").

    Args:
        col_name: Column name with or without unit suffix

    Returns:
        Column name without unit suffix

    Examples:
        "Revenue (K)" -> "Revenue"
        "Store.Total (count)" -> "Store.Total"
        "EPS.Basic ($)" -> "EPS.Basic"
        "Assets" -> "Assets"
    """
    # Remove pattern like " (unit)" at the end
    return re.sub(r'\s*\([^)]+\)\s*$', '', col_name).strip()


def match_columns(requested_cols: list[str], available_cols: list[str]) -> Result[dict[str, str], str]:
    """
    Match requested column patterns to available columns with partial matching.

    Supports both exact matches and prefix matches. For partial matches, the
    pattern must uniquely identify a single column.

    Args:
        requested_cols: List of column patterns to match (e.g., ["Store.Tot", "Revenue"])
        available_cols: List of available column names (e.g., ["Store.Total (count)", "Revenue (K)"])

    Returns:
        ok(dict) - Mapping of requested pattern to matched column name
        err(str) - Error if ambiguous match found

    Matching rules:
    1. Strip units from both requested and available columns
    2. Exact match (after stripping) takes priority
    3. If no exact match, try prefix match
    4. Prefix match must be unique (only one column starts with the pattern)

    Examples:
        requested: ["Store.Tot"]
        available: ["Store.Total (count)", "Store.States (count)"]
        -> ok({"Store.Tot": "Store.Total (count)"})

        requested: ["Store."]
        available: ["Store.Total (count)", "Store.States (count)"]
        -> err("Ambiguous match: 'Store.' matches multiple columns")
    """
    matches = {}

    for req in requested_cols:
        req_stripped = strip_units(req)

        # Try exact match first (after stripping units)
        exact_matches = [
            col for col in available_cols
            if strip_units(col) == req_stripped
        ]

        if exact_matches:
            # Exact match found (prefer first if multiple with same stripped name)
            matches[req] = exact_matches[0]
            continue

        # Try prefix match
        prefix_matches = [
            col for col in available_cols
            if strip_units(col).startswith(req_stripped)
        ]

        if len(prefix_matches) == 0:
            # No match found - skip this column (will be filtered out)
            continue
        elif len(prefix_matches) == 1:
            # Unique prefix match
            matches[req] = prefix_matches[0]
        else:
            # Ambiguous prefix match
            matched_names = [strip_units(col) for col in prefix_matches]
            return err(
                f"Ambiguous column pattern '{req}' matches multiple columns: {', '.join(matched_names)}"
            )

    return ok(matches)


def progress_bar(label: str = "Processing") -> Progress:
    """
    Create a standard progress bar for CLI commands.

    Usage:
        with progress_bar("Probing") as progress:
            task = progress.add_task("", total=len(items), current="")
            for item in items:
                progress.update(task, advance=1, current=f"{item}: done")

    Args:
        label: Label to show before the progress bar

    Returns:
        Configured Progress context manager
    """
    return Progress(
        TextColumn(f"  {label}:"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TextColumn("[cyan]{task.fields[current]}"),
        TimeRemainingColumn(),
    )
