"""
cli/shared.py - Shared validators and constants for CLI modules
"""

import re
import sys
import csv
import json
import argparse
import datetime
from tabulate import tabulate
from typing import Any, TypedDict


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

    # Filter data to selected columns, but always preserve 'pid' for delete command
    filtered_data = []
    for row in processed_data:
        filtered_row = {col: row[col] for col in valid_cols}
        # Preserve pid if it exists (needed for delete command)
        if 'pid' in row and 'pid' not in filtered_row:
            filtered_row['pid'] = row['pid']
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
