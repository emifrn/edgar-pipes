"""
CLI: calc

Calculate new columns based on arithmetic expressions.
Evaluates expressions on each row and adds computed columns to the data.

Examples:
    edgar report -t aeo -g Balance | calc "Current ratio = Current assets / Current liabilities"
    edgar report -t aeo -g Balance | calc "Working capital = Current assets - Current liabilities"
    edgar report -t aeo -g Balance | calc "Debt to equity = Total liabilities / Stockholders equity"
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

    # Apply expressions to each row
    calculated_data = []
    for row in cmd["data"]:
        new_row = dict(row)  # Copy original row

        for target_col, expression in parsed_expressions:
            result = _evaluate_expression(expression, new_row)
            if is_not_ok(result):
                return err(f"calc: {result[1]} in row {row}")

            new_row[target_col] = result[1]

        calculated_data.append(new_row)

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


def _evaluate_expression(expression: str, row: dict[str, Any]) -> Result[float | int | None, str]:
    """
    Safely evaluate arithmetic expression with column references.

    Args:
        expression: String like "Current assets / Current liabilities"
        row: Data row with column values

    Returns:
        ok(value) - Computed value
        err(str) - Evaluation error

    The expression is evaluated using Python's eval() in a restricted namespace
    that only contains column values and safe math operations.
    """

    # Build safe namespace with only row data
    # Column names with spaces/special chars are accessed as variables
    namespace = {}

    # Create variable names from column names
    # Replace spaces and special chars with underscores
    col_mapping = {}  # Maps sanitized names back to original column names

    for col_name, value in row.items():
        # Create a valid Python identifier from column name
        var_name = _sanitize_column_name(col_name)
        namespace[var_name] = value
        col_mapping[var_name] = col_name

    # Find all potential column names in the expression
    # We need to check if columns referenced in expression actually exist in row
    # Extract potential column names by looking for sequences of words in the expression
    # This is a heuristic - we look for patterns that could be column names

    # First, identify which columns from the expression exist in the row
    # We'll do a simple check: see if column replacement would work
    missing_columns = []
    for potential_col in _extract_column_names(expression):
        if potential_col not in row:
            missing_columns.append(potential_col)

    # If any column is missing, return None
    if missing_columns:
        return ok(None)

    # Replace column references in expression with sanitized variable names
    modified_expression = expression

    # Sort columns by length (longest first) to avoid partial matches
    # e.g., "Current assets current" should match "Current assets" before "Current"
    sorted_cols = sorted(row.keys(), key=len, reverse=True)

    for col_name in sorted_cols:
        var_name = _sanitize_column_name(col_name)
        # Use word boundary replacement to avoid partial matches
        # But we need to handle cases where column names have special chars
        modified_expression = modified_expression.replace(col_name, var_name)

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

    # Check if any referenced column is missing (None value)
    # This would cause issues in arithmetic
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
    """
    # Remove operators and parentheses to isolate potential identifiers
    # Keep only letters, digits, spaces, apostrophes
    cleaned = re.sub(r'[+\-*/()=<>]', ' | ', expression)

    # Split by pipe and clean up
    parts = [part.strip() for part in cleaned.split('|')]

    # Filter out empty strings, numbers, and known function names
    known_functions = {'abs', 'round', 'min', 'max', 'sum', 'sqrt', 'pow', 'floor', 'ceil'}
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
