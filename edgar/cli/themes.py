"""
cli/themes.py - Rich-based table theming and formatting for Edgar CLI

Provides configurable visual themes using Rich library with zebra striping,
sophisticated color management, and financial data awareness.
"""

import os
import sys
from typing import Any, Optional
from io import StringIO

try:
    from rich.console import Console
    from rich.table import Table
    from rich.style import Style
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    # Fallback to basic tabulate if Rich not available
    from tabulate import tabulate


def should_use_color() -> bool:
    """Determine if color output should be used."""
    if not HAS_RICH:
        return False
    
    # Don't use color if output is redirected
    if not sys.stdout.isatty():
        return False
    
    # Respect NO_COLOR environment variable
    if os.environ.get('NO_COLOR'):
        return False
    
    # Check for explicit color preference
    force_color = os.environ.get('FORCE_COLOR')
    if force_color:
        return True
    
    # Default: use color in interactive terminals
    return True


class BaseTheme:
    """Base theme class for Rich table formatting."""
    
    def __init__(self):
        self.use_color = should_use_color()
        self.console = Console(force_terminal=self.use_color) if HAS_RICH else None
    
    # Theme properties
    @property
    def show_header(self) -> bool:
        return True
    
    @property
    def show_lines(self) -> bool:
        return False
    
    @property
    def show_edge(self) -> bool:
        return True
    
    @property
    def padding(self) -> tuple[int, int]:
        return (0, 1)  # (vertical, horizontal)
    
    @property
    def header_style(self) -> str:
        return "bold"
    
    @property
    def row_styles(self) -> list[str]:
        return ["", ""]  # No zebra striping by default
    
    @property
    def box_style(self) -> str | None:
        """Box style for Rich table. None removes all borders."""
        return "default"  # Use Rich's default box style
    
    # Column-specific styles
    def get_column_style(self, column_name: str, column_type: str) -> str:
        """Get Rich style string for a column."""
        return ""
    
    def detect_column_type(self, column_name: str) -> str:
        """Detect semantic column type for styling."""
        name_lower = column_name.lower()
        
        if name_lower in ['ticker', 'symbol']:
            return 'ticker'
        elif 'date' in name_lower:
            return 'date'
        elif name_lower in ['pid', 'gid', 'cid', 'uid', 'rid', 'fid', 'xid', 'unid', 'did']:
            return 'id'
        elif 'group' in name_lower and 'name' in name_lower:
            return 'group_name'
        elif name_lower in ['name', 'concept_name']:
            return 'concept_name'
        elif name_lower == 'status':
            return 'status'
        elif name_lower == 'type':
            return 'type'
        elif any(keyword in name_lower for keyword in ['count', 'value', 'amount']):
            return 'number'
        else:
            return 'default'


class DefaultTheme(BaseTheme):
    """Clean default theme with minimal styling."""
    
    @property
    def header_style(self) -> str:
        return "bold white"
    
    def get_column_style(self, column_name: str, column_type: str) -> str:
        return ""


class FinancialLightTheme(BaseTheme):
    """Financial data theme optimized for light terminals."""
    
    @property
    def header_style(self) -> str:
        return "bold blue"
    
    @property
    def row_styles(self) -> list[str]:
        return ["", "on grey11"]  # Zebra striping
    
    def get_column_style(self, column_name: str, column_type: str) -> str:
        styles = {
            'ticker': 'bold blue',
            'date': 'green',
            'id': 'magenta',
            'group_name': 'cyan',
            'concept_name': 'white',
            'type': 'yellow',
            'number': 'bright_yellow',
            'status': 'green',  # Will be overridden based on value
            'default': ''
        }
        return styles.get(column_type, '')


class FinancialDarkTheme(BaseTheme):
    """Financial data theme optimized for dark terminals."""
    
    @property
    def header_style(self) -> str:
        return "bold bright_cyan"
    
    @property
    def row_styles(self) -> list[str]:
        return ["", "on grey15"]  # Zebra striping
    
    def get_column_style(self, column_name: str, column_type: str) -> str:
        styles = {
            'ticker': 'bold bright_blue',
            'date': 'bright_green',
            'id': 'bright_magenta',
            'group_name': 'bright_cyan',
            'concept_name': 'bright_white',
            'type': 'bright_yellow',
            'number': 'yellow',
            'status': 'bright_green',  # Will be overridden based on value
            'default': ''
        }
        return styles.get(column_type, '')


class MinimalLightTheme(BaseTheme):
    """Clean minimal theme for light terminals."""
    
    @property
    def header_style(self) -> str:
        return "bold"
    
    @property
    def row_styles(self) -> list[str]:
        return ["", "dim"]
    
    def get_column_style(self, column_name: str, column_type: str) -> str:
        if column_type == 'ticker':
            return 'bold'
        return ''


class MinimalDarkTheme(BaseTheme):
    """Clean minimal theme for dark terminals."""
    
    @property
    def header_style(self) -> str:
        return "bold bright_white"
    
    @property
    def row_styles(self) -> list[str]:
        return ["", "dim"]
    
    def get_column_style(self, column_name: str, column_type: str) -> str:
        if column_type == 'ticker':
            return 'bold bright_white'
        return ''


class GridLightTheme(FinancialLightTheme):
    """Financial light theme with full grid borders."""
    
    @property
    def show_lines(self) -> bool:
        return True


class GridDarkTheme(FinancialDarkTheme):
    """Financial dark theme with full grid borders."""
    
    @property
    def show_lines(self) -> bool:
        return True


# Nobox theme variants - inherit all styling but remove borders/separators
class NoBoxFinancialLightTheme(FinancialLightTheme):
    """Financial light theme with no borders or separators."""
    
    @property
    def box_style(self) -> str | None:
        return None


class NoBoxFinancialDarkTheme(FinancialDarkTheme):
    """Financial dark theme with no borders or separators."""
    
    @property
    def box_style(self) -> str | None:
        return None


class NoBoxMinimalLightTheme(MinimalLightTheme):
    """Minimal light theme with no borders or separators."""
    
    @property
    def box_style(self) -> str | None:
        return None


class NoBoxMinimalDarkTheme(MinimalDarkTheme):
    """Minimal dark theme with no borders or separators."""
    
    @property
    def box_style(self) -> str | None:
        return None


# Theme registry
THEMES = {
    "default": DefaultTheme,
    "financial": FinancialLightTheme,  # Alias for light
    "financial-light": FinancialLightTheme,
    "financial-dark": FinancialDarkTheme,
    "minimal": MinimalLightTheme,  # Alias for light
    "minimal-light": MinimalLightTheme,
    "minimal-dark": MinimalDarkTheme,
    "grid": GridLightTheme,  # Alias for light
    "grid-light": GridLightTheme,
    "grid-dark": GridDarkTheme,
    "nobox": NoBoxFinancialLightTheme,  # Alias for nobox-light
    "nobox-light": NoBoxFinancialLightTheme,
    "nobox-dark": NoBoxFinancialDarkTheme,
    "nobox-minimal": NoBoxMinimalLightTheme,  # Alias for nobox-minimal-light
    "nobox-minimal-light": NoBoxMinimalLightTheme,
    "nobox-minimal-dark": NoBoxMinimalDarkTheme,
}


def get_theme(theme_name: str = "default") -> BaseTheme:
    """Get theme instance by name."""
    theme_class = THEMES.get(theme_name, DefaultTheme)
    return theme_class()


def style_cell_value(value: Any, column_type: str, row_index: int) -> str:
    """Apply value-specific styling (for status fields, etc.)."""
    str_value = str(value) if value is not None else ""
    
    # Special handling for status column
    if column_type == 'status':
        # Handle symbols
        if str_value == '✓':
            return f"[green]{str_value}[/green]"
        elif str_value == '✗':
            return f"[red]{str_value}[/red]"
        # Handle text-based status (existing logic)
        value_lower = str_value.lower()
        if value_lower in ['ok', 'success', 'deleted']:
            return f"[green]{str_value}[/green]"
        elif value_lower in ['error', 'failed']:
            return f"[red]{str_value}[/red]"
        elif value_lower == 'dry-run':
            return f"[yellow]{str_value}[/yellow]"
    
    return str_value


def themed_table(data: list[dict], headers: list[str] = None, theme_name: str = "default") -> str:
    """Generate themed table from data using Rich."""
    if not data:
        return ""
    
    if not HAS_RICH:
        # Fallback to tabulate if Rich not available
        from tabulate import tabulate
        if headers is None:
            headers = list(data[0].keys())
        table_data = [[row.get(h, "") for h in headers] for row in data]
        return tabulate(table_data, headers=headers, tablefmt="simple")
    
    # Use provided headers or derive from first row
    if headers is None:
        headers = list(data[0].keys())
    
    theme = get_theme(theme_name)
    
    # Create Rich table with theme-specific box style
    table_kwargs = {
        "show_header": theme.show_header,
        "header_style": theme.header_style,
        "show_lines": theme.show_lines,
        "show_edge": theme.show_edge,
        "padding": theme.padding,
        "row_styles": theme.row_styles
    }
    
    # Add box parameter if theme specifies it
    if hasattr(theme, 'box_style') and theme.box_style is not None:
        if theme.box_style == "default":
            pass  # Use Rich's default box
        else:
            table_kwargs["box"] = theme.box_style
    elif hasattr(theme, 'box_style') and theme.box_style is None:
        table_kwargs["box"] = None  # Remove all borders and separators
    
    table = Table(**table_kwargs)
    
    # Add columns with appropriate styling
    for header in headers:
        column_type = theme.detect_column_type(header)
        column_style = theme.get_column_style(header, column_type)
        table.add_column(header, style=column_style)
    
    # Add rows with value-specific styling
    for row_index, row in enumerate(data):
        styled_row = []
        for header in headers:
            value = row.get(header, "")
            column_type = theme.detect_column_type(header)
            styled_value = style_cell_value(value, column_type, row_index)
            styled_row.append(styled_value)
        table.add_row(*styled_row)
    
    # Render to string
    console = Console(file=StringIO(), force_terminal=theme.use_color, width=None)
    console.print(table)
    return console.file.getvalue().rstrip()


def get_default_theme() -> str:
    """Get default theme name from environment or config."""
    return os.environ.get('EDGAR_PIPES_THEME', 'financial-light')


def list_available_themes() -> list[str]:
    """Return list of available theme names."""
    return sorted(THEMES.keys())
