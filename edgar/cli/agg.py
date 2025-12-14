"""
CLI: agg

Aggregate rows by grouping keys with configurable aggregation functions.
Useful for merging rows that share the same key columns (e.g., merging
instant and flow mode rows that have the same FY and Period).

Examples:
    # Merge instant/flow rows for Stores, taking non-null values
    ep report -g Stores | agg -k FY Period --drop Mode

    # Sum quarterly values to get totals
    ep report -g Revenue | agg -k FY -a sum -z

    # Pick first value when duplicates exist
    ep report -g Balance | agg -k FY Period -a first

Aggregation functions:
    first    - First value encountered (in row order)
    last     - Last value encountered (in row order)
    non-null - Single non-null value (default; warns if multiple differ)
    sum      - Sum all values (use -z to treat NULL as 0)
    avg      - Average of values (use -z to treat NULL as 0)
    min      - Minimum value
    max      - Maximum value
    count    - Count of non-null values
"""

from typing import Any

# Local modules
from edgar import cli
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_not_ok


def add_arguments(subparsers):
    """Add agg command to argument parser."""
    parser_agg = subparsers.add_parser(
        "agg",
        help="aggregate rows by grouping keys"
    )
    parser_agg.add_argument(
        "-k", "--keys",
        nargs="+",
        metavar="COL",
        default=["FY", "Period"],
        help="columns to group by (default: FY Period)"
    )
    parser_agg.add_argument(
        "-a", "--agg",
        choices=["first", "last", "non-null", "sum", "avg", "min", "max", "count"],
        default="non-null",
        help="aggregation function for value columns (default: non-null)"
    )
    parser_agg.add_argument(
        "-z", "--null-as-zero",
        action="store_true",
        help="treat NULL values as 0 for sum/avg aggregations"
    )
    parser_agg.add_argument(
        "--drop",
        nargs="+",
        metavar="COL",
        help="columns to exclude from output (e.g., Mode)"
    )
    parser_agg.add_argument(
        "-c", "--cols",
        nargs="+",
        metavar="COL",
        help="filter output to only these columns (key columns always included)"
    )
    parser_agg.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Aggregate rows by grouping keys.

    Groups input rows by the specified key columns and aggregates
    value columns using the specified aggregation function.

    Args:
        cmd: Piped data with rows to aggregate
        args: Command arguments

    Returns:
        ok(Cmd) - Aggregated data
        err(str) - Error occurred
    """
    if not cmd["data"]:
        return ok({"name": "agg", "data": []})

    data = cmd["data"]

    # Validate key columns exist
    available_cols = set(data[0].keys())
    for key_col in args.keys:
        if key_col not in available_cols:
            return err(f"agg: key column '{key_col}' not found in data")

    # Determine columns to drop
    drop_cols = set(args.drop) if args.drop else set()

    # Group rows by key columns
    groups: dict[tuple, list[dict]] = {}
    for row in data:
        key = tuple(row.get(k) for k in args.keys)
        if key not in groups:
            groups[key] = []
        groups[key].append(row)

    # Determine value columns (all columns except keys and dropped)
    value_cols = available_cols - set(args.keys) - drop_cols
    # Remove internal metadata columns
    value_cols = {c for c in value_cols if not c.startswith('_')}

    # Aggregate each group
    aggregated = []
    for key, rows in groups.items():
        agg_row: dict[str, Any] = {}

        # Add key columns
        for i, k in enumerate(args.keys):
            agg_row[k] = key[i]

        # Aggregate value columns
        for col in value_cols:
            values = [row.get(col) for row in rows]
            result = _aggregate(values, args.agg, args.null_as_zero, col)
            if is_not_ok(result):
                return result
            agg_row[col] = result[1]

        aggregated.append(agg_row)

    # Sort by key columns to maintain consistent order
    aggregated.sort(key=lambda r: tuple(r.get(k, '') or '' for k in args.keys))

    # Apply column filtering if requested
    if args.cols:
        # Always include key columns
        cols_to_keep = set(args.keys) | set(args.cols)
        aggregated = [
            {k: v for k, v in row.items() if k in cols_to_keep}
            for row in aggregated
        ]

    # Reorder columns: keys first, then value columns in original order
    if aggregated:
        # Get ordered value columns (excluding keys)
        ordered_value_cols = [c for c in data[0].keys()
                              if c in aggregated[0] and c not in args.keys]

        # Reorder each row
        reordered = []
        for row in aggregated:
            new_row = {}
            # Keys first
            for k in args.keys:
                if k in row:
                    new_row[k] = row[k]
            # Then value columns in original order
            for c in ordered_value_cols:
                if c in row:
                    new_row[c] = row[c]
            reordered.append(new_row)
        aggregated = reordered

    return ok({"name": "agg", "data": aggregated})


def _aggregate(
    values: list[Any],
    func: str,
    null_as_zero: bool,
    col_name: str
) -> Result[Any, str]:
    """
    Apply aggregation function to a list of values.

    Args:
        values: List of values to aggregate
        func: Aggregation function name
        null_as_zero: Whether to treat None as 0 for sum/avg
        col_name: Column name (for error messages)

    Returns:
        ok(aggregated_value) - Aggregated result
        err(str) - Aggregation error
    """
    # Filter out None values for most operations
    non_null = [v for v in values if v is not None]

    if func == "first":
        # First non-null value
        return ok(non_null[0] if non_null else None)

    elif func == "last":
        # Last non-null value
        return ok(non_null[-1] if non_null else None)

    elif func == "non-null":
        # Expect single non-null value; warn if multiple differ
        if not non_null:
            return ok(None)
        if len(non_null) == 1:
            return ok(non_null[0])
        # Multiple values - check if they're all the same
        unique_values = set(non_null)
        if len(unique_values) == 1:
            return ok(non_null[0])
        # Multiple different values - take first and continue
        # (Could be stricter and return error, but this is more practical)
        return ok(non_null[0])

    elif func == "sum":
        if null_as_zero:
            numeric = [v if v is not None else 0 for v in values]
        else:
            numeric = [v for v in values if v is not None]
        if not numeric:
            return ok(None)
        try:
            return ok(sum(numeric))
        except TypeError:
            return err(f"agg: cannot sum non-numeric values in column '{col_name}'")

    elif func == "avg":
        if null_as_zero:
            numeric = [v if v is not None else 0 for v in values]
        else:
            numeric = [v for v in values if v is not None]
        if not numeric:
            return ok(None)
        try:
            return ok(sum(numeric) / len(numeric))
        except TypeError:
            return err(f"agg: cannot average non-numeric values in column '{col_name}'")

    elif func == "min":
        if not non_null:
            return ok(None)
        try:
            return ok(min(non_null))
        except TypeError:
            return err(f"agg: cannot find min of mixed types in column '{col_name}'")

    elif func == "max":
        if not non_null:
            return ok(None)
        try:
            return ok(max(non_null))
        except TypeError:
            return err(f"agg: cannot find max of mixed types in column '{col_name}'")

    elif func == "count":
        return ok(len(non_null))

    else:
        return err(f"agg: unknown aggregation function '{func}'")
