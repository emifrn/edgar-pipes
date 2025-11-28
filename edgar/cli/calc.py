"""
CLI: calc

Calculate new columns based on arithmetic expressions.
Evaluates expressions on each row and adds computed columns to the data.

The calc command strips unit suffixes from column names (e.g., "(K)", "($)", "(%)")
before evaluation, so expressions reference simple concept names without units.

Examples:
    ep report -t aeo -g Balance | calc "Current ratio = Current assets / Current liabilities"
    ep report -t bke -g Operations | calc "Gross margin = (Revenue - COGS) / Revenue * 100"
    ep report -t bke -g Operations | calc "Net margin = Income.Net / Revenue * 100"

Note: Even if report shows "Revenue (K)", reference it as just "Revenue" in formulas.
"""

import re
import sys
import math
from typing import Any

# Local modules
from edgar import cli
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_not_ok


def add_arguments(subparsers):
    """Add calc command to argument parser."""
    parser_calc = subparsers.add_parser(
        "calc",
        help="calculate new columns from expressions"
    )
    parser_calc.add_argument(
        "expressions",
        nargs="+",
        metavar="EXPR",
        help='expressions like "New column = Column A + Column B"'
    )
    parser_calc.add_argument(
        "-z", "--null-as-zero",
        action="store_true",
        help="treat NULL values as 0 in arithmetic operations"
    )
    parser_calc.add_argument(
        "-c", "--cols",
        metavar="X",
        nargs="+",
        help="filter output columns (metadata columns FY, Period, Mode always included)"
    )
    parser_calc.add_argument(
        "-w", "--rolling",
        metavar="N",
        type=int,
        help="enable rolling window calculations with window size N (backward-looking)"
    )
    parser_calc.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Calculate new columns based on arithmetic expressions.

    Args:
        cmd: Piped data
        args: Command arguments with expressions

    Returns:
        ok(Cmd) - Data with computed columns
        err(str) - Error occurred
    """

    if not cmd["data"]:
        return ok({"name": "calc", "data": []})

    # Parse all expressions
    parsed_expressions = []
    for expr_str in args.expressions:
        result = _parse_expression(expr_str)
        if is_not_ok(result):
            return result
        parsed_expressions.append(result[1])

    # Strip units from column names in input data for cleaner calculations
    # Convert {"Revenue (K)": 1000} -> {"Revenue": 1000}
    stripped_data = []
    for row in cmd["data"]:
        # Strip units from all column names
        stripped_row = {}
        for col_name, value in row.items():
            base_name = _strip_units(col_name)
            stripped_row[base_name] = value
        stripped_data.append(stripped_row)

    # Build rolling windows if --rolling is specified
    windows = None
    if args.rolling:
        windows = _build_rolling_windows(stripped_data, args.rolling)

    # Apply expressions to each row
    calculated_data = []
    for idx, row in enumerate(stripped_data):
        # Get rolling window for this row if in rolling mode
        window_data = windows[idx] if windows is not None else None

        # Apply expressions to row
        for target_col, expression in parsed_expressions:
            result = _evaluate_expression(
                expression, row,
                null_as_zero=args.null_as_zero,
                window_data=window_data
            )
            if is_not_ok(result):
                return err(f"calc: {result[1]} in row {row}")

            row[target_col] = result[1]

        calculated_data.append(row)

    # Apply column filtering if requested
    if calculated_data:
        # Metadata columns that should always be included
        metadata_cols = ["FY", "Period", "Mode"]

        # Build column list: metadata + requested columns (or all if none requested)
        if args.cols:
            # Include metadata columns + user-specified columns
            cols_with_metadata = metadata_cols + [c for c in args.cols if c not in metadata_cols]
            default_cols = list(calculated_data[0].keys())
            result = cli.shared.process_cols(calculated_data, cols_with_metadata, default_cols)
        else:
            # No filtering - show all columns
            default_cols = list(calculated_data[0].keys())
            result = cli.shared.process_cols(calculated_data, None, default_cols)

        if is_not_ok(result):
            return result
        calculated_data, _ = result[1]

    return ok({"name": "calc", "data": calculated_data})


def _parse_expression(expr_str: str) -> Result[tuple[str, str], str]:
    """
    Parse expression string into (target_column, expression).

    Args:
        expr_str: String like "Total = A + B" or "A + B"

    Returns:
        ok((target_column, expression)) - Parsed components
        err(str) - Parse error

    Examples:
        "Current ratio = Current assets / Current liabilities"
          -> ("Current ratio", "Current assets / Current liabilities")
        "Profit margin = Net income / Revenue * 100"
          -> ("Profit margin", "Net income / Revenue * 100")
    """

    # Check if expression has assignment
    if "=" in expr_str:
        parts = expr_str.split("=", 1)
        if len(parts) != 2:
            return err(f"calc: invalid expression format: '{expr_str}'")

        target_col = parts[0].strip()
        expression = parts[1].strip()

        if not target_col:
            return err(f"calc: empty column name in expression: '{expr_str}'")
        if not expression:
            return err(f"calc: empty expression in: '{expr_str}'")

        return ok((target_col, expression))
    else:
        # No assignment - use the expression itself as column name
        expression = expr_str.strip()
        return ok((expression, expression))


def _strip_units(col_name: str) -> str:
    """
    Strip unit suffix from column name.

    Examples:
        "Revenue (K)" -> "Revenue"
        "EPS.Basic ($)" -> "EPS.Basic"
        "Assets" -> "Assets"
    """
    # Remove pattern like " (unit)" at the end
    return re.sub(r'\s*\([^)]+\)\s*$', '', col_name).strip()


def _evaluate_expression(expression: str, row: dict[str, Any], null_as_zero: bool = False, window_data: list[dict] | None = None) -> Result[float | int | None, str]:
    """
    Safely evaluate arithmetic expression with column references.

    Args:
        expression: String like "Current assets / Current liabilities"
        row: Data row with column values (units already stripped)
        null_as_zero: If True, treat NULL values as 0 in arithmetic
        window_data: Optional rolling window data for rolling calculations

    Returns:
        ok(value) - Computed value
        err(str) - Evaluation error

    The expression is evaluated using Python's eval() in a restricted namespace
    that only contains column values and safe math operations.

    When window_data is provided, rolling aggregation functions are available:
    - rolling_sum(column_name) - Sum of column over window
    - rolling_avg(column_name) - Average of column over window
    - rolling_min(column_name) - Minimum of column over window
    - rolling_max(column_name) - Maximum of column over window
    """

    # Build safe namespace with row data
    # Column names with spaces/special chars are converted to valid Python identifiers
    namespace = {}

    for col_name, value in row.items():
        var_name = _sanitize_column_name(col_name)
        namespace[var_name] = value

    # Find all potential column names in the expression and check they exist
    missing_columns = []
    extracted_cols = _extract_column_names(expression)
    for potential_col in extracted_cols:
        if potential_col not in row:
            missing_columns.append(potential_col)

    # If any column is missing, return None
    if missing_columns:
        return ok(None)

    # Replace column references in expression with sanitized variable names
    # Sort by length (longest first) to avoid partial matches
    # BUT: Don't replace column names inside quoted strings (for function arguments)
    modified_expression = expression
    sorted_columns = sorted(row.keys(), key=len, reverse=True)

    # Split expression into parts outside and inside quotes to avoid replacing inside strings
    for col_name in sorted_columns:
        var_name = _sanitize_column_name(col_name)
        # Only replace outside of quoted strings
        # Use regex to avoid replacing inside "..." or '...'
        # Replace col_name with var_name only when not inside quotes
        # Simple approach: split by quotes, replace in non-quoted parts, rejoin
        parts = []
        in_quote = None
        current = ""
        i = 0
        while i < len(modified_expression):
            c = modified_expression[i]
            if c in ('"', "'") and (i == 0 or modified_expression[i-1] != '\\'):
                if in_quote is None:
                    # Starting a quoted section - process accumulated non-quoted part
                    parts.append(current.replace(col_name, var_name))
                    current = c
                    in_quote = c
                elif in_quote == c:
                    # Ending a quoted section - keep as-is
                    parts.append(current + c)
                    current = ""
                    in_quote = None
                else:
                    current += c
            else:
                current += c
            i += 1
        # Process final part
        if in_quote is None:
            parts.append(current.replace(col_name, var_name))
        else:
            parts.append(current)
        modified_expression = ''.join(parts)

    # Add safe math functions to namespace
    safe_functions = {
        'abs': abs,
        'round': round,
        'min': min,
        'max': max,
        'sum': sum,
        'sqrt': math.sqrt,
        'pow': pow,
        'floor': math.floor,
        'ceil': math.ceil,
    }
    namespace.update(safe_functions)

    # Add rolling window functions if window data is provided
    if window_data is not None:
        namespace['rolling_sum'] = lambda col: _rolling_sum(window_data, col, null_as_zero)
        namespace['rolling_avg'] = lambda col: _rolling_avg(window_data, col, null_as_zero)
        namespace['rolling_min'] = lambda col: _rolling_min(window_data, col)
        namespace['rolling_max'] = lambda col: _rolling_max(window_data, col)

    # Handle NULL values
    if null_as_zero:
        # Treat NULL as 0 in arithmetic
        for var_name in list(namespace.keys()):
            if var_name not in safe_functions and namespace[var_name] is None:
                namespace[var_name] = 0
    else:
        # Check if any referenced column has None value
        for var_name, value in namespace.items():
            if var_name in safe_functions:
                continue  # Skip function names
            if value is None:
                return ok(None)  # Return None if any input is None

    # Evaluate expression
    try:
        result = eval(modified_expression, {"__builtins__": {}}, namespace)
        return ok(result)
    except ZeroDivisionError:
        return ok(None)  # Return None for division by zero
    except NameError as e:
        # Column referenced in expression doesn't exist in row
        return ok(None)  # Return None for missing columns
    except SyntaxError as e:
        # Debug: show what went wrong
        return err(f"syntax error in '{modified_expression}' (from '{expression}'): {e}")
    except Exception as e:
        return err(f"failed to evaluate '{expression}': {e}")


def _extract_column_names(expression: str) -> list[str]:
    """
    Extract potential column names from expression.

    This is a heuristic that finds sequences of alphanumeric characters
    and spaces that could be column names.

    Examples:
        "Current assets / Current liabilities" -> ["Current assets", "Current liabilities"]
        "Net income + Other income" -> ["Net income", "Other income"]
        'rolling_sum("Revenue")' -> [] (string literals are skipped)
    """
    # Remove string literals first (anything in quotes)
    # This prevents column names inside function calls from being extracted
    no_strings = re.sub(r'"[^"]*"', '', expression)
    no_strings = re.sub(r"'[^']*'", '', no_strings)

    # Remove operators and parentheses to isolate potential identifiers
    # Keep only letters, digits, spaces, apostrophes
    cleaned = re.sub(r'[+\-*/()=<>]', ' | ', no_strings)

    # Split by pipe and clean up
    parts = [part.strip() for part in cleaned.split('|')]

    # Filter out empty strings, numbers, and known function names
    known_functions = {
        'abs', 'round', 'min', 'max', 'sum', 'sqrt', 'pow', 'floor', 'ceil',
        'rolling_sum', 'rolling_avg', 'rolling_min', 'rolling_max'
    }
    column_names = []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Skip if it's a number
        try:
            float(part)
            continue
        except ValueError:
            pass
        # Skip if it's a known function
        if part.lower() in known_functions:
            continue
        # Otherwise, treat as potential column name
        column_names.append(part)

    return column_names


def _sanitize_column_name(col_name: str) -> str:
    """
    Convert column name to valid Python identifier.

    Examples:
        "Current assets" -> "Current_assets"
        "Stockholders' equity" -> "Stockholders_equity"
        "P/E ratio" -> "P_E_ratio"
    """
    # Replace non-alphanumeric chars with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', col_name)

    # Ensure it doesn't start with a digit
    if sanitized and sanitized[0].isdigit():
        sanitized = '_' + sanitized

    return sanitized


def _build_rolling_windows(data: list[dict], window_size: int) -> dict[int, list[dict]]:
    """
    Build backward-looking rolling windows for each row index.

    Args:
        data: List of data rows
        window_size: Number of rows to include in each window

    Returns:
        Dictionary mapping row index to its rolling window (list of rows)

    Example:
        For window_size=4 and data with 10 rows:
        - Index 0: window contains [row 0] (only 1 row available)
        - Index 3: window contains [row 0, row 1, row 2, row 3] (full 4 rows)
        - Index 9: window contains [row 6, row 7, row 8, row 9] (full 4 rows)
    """
    windows = {}
    for i in range(len(data)):
        start = max(0, i - window_size + 1)  # Backward-looking window
        windows[i] = data[start:i+1]
    return windows


def _rolling_sum(window_data: list[dict], column: str, null_as_zero: bool = False) -> float | int | None:
    """
    Calculate sum of column values across rolling window.

    Args:
        window_data: List of rows in the current window
        column: Column name to aggregate
        null_as_zero: If True, treat None values as 0

    Returns:
        Sum of values, or None if all values are None
    """
    values = []
    for row in window_data:
        val = row.get(column)
        if val is not None:
            values.append(val)
        elif null_as_zero:
            values.append(0)

    return sum(values) if values else None


def _rolling_avg(window_data: list[dict], column: str, null_as_zero: bool = False) -> float | None:
    """
    Calculate average of column values across rolling window.

    Args:
        window_data: List of rows in the current window
        column: Column name to aggregate
        null_as_zero: If True, treat None values as 0

    Returns:
        Average of values, or None if all values are None
    """
    values = []
    for row in window_data:
        val = row.get(column)
        if val is not None:
            values.append(val)
        elif null_as_zero:
            values.append(0)

    return sum(values) / len(values) if values else None


def _rolling_min(window_data: list[dict], column: str) -> float | int | None:
    """
    Calculate minimum of column values across rolling window.

    Args:
        window_data: List of rows in the current window
        column: Column name to aggregate

    Returns:
        Minimum value, or None if all values are None
    """
    values = [row.get(column) for row in window_data if row.get(column) is not None]
    return min(values) if values else None


def _rolling_max(window_data: list[dict], column: str) -> float | int | None:
    """
    Calculate maximum of column values across rolling window.

    Args:
        window_data: List of rows in the current window
        column: Column name to aggregate

    Returns:
        Maximum value, or None if all values are None
    """
    values = [row.get(column) for row in window_data if row.get(column) is not None]
    return max(values) if values else None
