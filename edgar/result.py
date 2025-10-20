"""
result.py - Functional Result pattern for explicit error handling
"""

from typing import Tuple, Union, Callable, TypeVar


__all__ = ['Result', 'ok', 'err', 'is_ok', 'is_not_ok', 'unwrap', 'unwrap_or']


T = TypeVar('T')
E = TypeVar('E')
U = TypeVar('U')


# Result is just a tuple: (success: bool, value_or_error)
Result = Tuple[bool, Union[T, E]]


def ok(value: T) -> Result[T, E]:
    """Create a successful Result containing the given value."""
    return (True, value)


def err(error: E) -> Result[T, E]:
    """Create an error Result containing the given error."""
    return (False, error)


def is_ok(result: Result) -> bool:
    """Return True if the Result represents success."""
    return result[0]


def is_not_ok(result: Result) -> bool:
    """Return True if the Result represents an error."""
    return not result[0]


def unwrap(result: Result[T, E]) -> T:
    """Extract the value from an Ok Result. Raises RuntimeError if Err."""
    if result[0]:
        return result[1]
    raise RuntimeError(f"Called unwrap on error: {result[1]}")


def unwrap_or(result: Result[T, E], default: T) -> T:
    """Extract the value from Result, or return default if Err."""
    return result[1] if result[0] else default


def unwrap_err(result: Result[T, E]) -> E:
    """Extract error from Err Result. Raises if Ok."""
    if not result[0]:
        return result[1]
    raise RuntimeError("Called unwrap_err on Ok result")


def map_result(result: Result[T, E], func: Callable[[T], U]) -> Result[U, E]:
    """Apply function to Ok value, pass through Err unchanged."""
    if result[0]:
        return ok(func(result[1]))
    return result
