"""Configuration management for edgar-pipes.

Loads configuration with the following precedence (highest to lowest):
1. Config file (~/.config/edgar-pipes/config.toml) - user agent, theme
2. Workspace file (.ft.toml) - database, journals, default ticker
3. Built-in defaults
"""

import os
import sys
import tomllib
from typing import Any
from pathlib import Path


DEFAULT_CONFIG = {
    "edgar": {
        "user_agent": "edgar-pipes/0.3.2",  # Fallback (not ideal, prompt user)
    },
    "output": {
        "theme": "nobox-minimal",
    },
}


def get_config_path() -> Path:
    """Get config file path using XDG_CONFIG_HOME."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(xdg_config).expanduser() / "edgar-pipes" / "config.toml"


def load_config() -> dict[str, Any]:
    """
    Load configuration with precedence:
    1. Environment variables (highest) - user agent, theme only
    2. Config file (~/.config/edgar-pipes/config.toml)
    3. Built-in defaults (lowest)

    Note: Workspace paths (database, journals) come from ft.toml, not this config.
    """
    # Start with defaults
    config = {
        "edgar": DEFAULT_CONFIG["edgar"].copy(),
        "output": DEFAULT_CONFIG["output"].copy(),
    }

    # 1. Load from config file if it exists
    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                file_config = tomllib.load(f)
                # Merge file config into defaults
                for section, values in file_config.items():
                    if section in config and isinstance(values, dict):
                        config[section].update(values)
        except Exception as e:
            print(f"Warning: Could not load config file: {e}", file=sys.stderr)

    # 2. Override with environment variables (user agent and theme only)
    env_overrides = {
        "EDGAR_PIPES_USER_AGENT": ("edgar", "user_agent"),
        "EDGAR_PIPES_THEME": ("output", "theme"),
    }

    for env_var, (section, key) in env_overrides.items():
        value = os.getenv(env_var)
        if value:
            config[section][key] = value

    return config


def init_config_interactive() -> bool:
    """
    Interactive first-run configuration setup.
    Returns True if config was created, False if it already exists.
    """
    config_path = get_config_path()

    # Don't re-run if config already exists
    if config_path.exists():
        return False

    print("\nWelcome to edgar-pipes!", file=sys.stderr)
    print("\nThe SEC requires a user-agent for API requests.", file=sys.stderr)
    print('Please provide your name and email (e.g., "John Doe john@example.com"):', file=sys.stderr)
    print("> ", end="", file=sys.stderr)
    user_agent = input().strip()

    if not user_agent:
        print("\nNo user-agent provided. Using default (not recommended).", file=sys.stderr)
        return False

    # Create config directory
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Write config file
    config_content = f"""# Edgar-pipes configuration file

[edgar]
# Your identity for SEC EDGAR API requests
user_agent = "{user_agent}"

[output]
# Default table theme
theme = "nobox-minimal"
"""

    with open(config_path, "w") as f:
        f.write(config_content)

    print(f"\n✓ Configuration saved to {config_path}", file=sys.stderr)
    print("  You can edit this file anytime to change settings.", file=sys.stderr)
    print("  Use 'ep config show' to view current configuration.\n", file=sys.stderr)

    return True


def find_workspace_config(start_dir: Path | None = None) -> Path | None:
    """
    Find ft.toml by walking up directory tree from start_dir.

    Args:
        start_dir: Directory to start search from (default: current directory)

    Returns:
        Path to ft.toml file if found, None otherwise
    """
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    # Walk up directory tree
    while True:
        ft_config = current / "ft.toml"
        if ft_config.exists():
            return ft_config

        # Check if we've reached the root
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            return None

        current = parent


def load_workspace_config(context_workspace: str | None = None) -> tuple[Path, dict[str, Any]]:
    """
    Load workspace configuration from ft.toml file.

    Args:
        context_workspace: Workspace path from pipeline context (if available)

    Returns:
        Tuple of (workspace_root, workspace_config)

    Raises:
        RuntimeError: If no ft.toml file found
    """
    # If context provides workspace, use that directory to find ft.toml
    if context_workspace:
        start_dir = Path(context_workspace)
    else:
        start_dir = Path.cwd()

    ft_config_path = find_workspace_config(start_dir)

    if ft_config_path is None:
        error_msg = f"""No ft.toml workspace configuration found.

Searched from: {start_dir}

Create a ft.toml file in your workspace directory:

[workspace]
ticker = "AAPL"  # Optional: default ticker

[edgar-pipes]
database = "db/edgar.db"
journals = "src/journals"

See https://github.com/emifrn/edgar-pipes for more information."""
        raise RuntimeError(error_msg)

    # Load the TOML file
    try:
        with open(ft_config_path, "rb") as f:
            workspace_config = tomllib.load(f)
    except Exception as e:
        raise RuntimeError(f"Error loading {ft_config_path}: {e}")

    # Validate required sections
    if "edgar-pipes" not in workspace_config:
        raise RuntimeError(f"{ft_config_path}: Missing required [edgar-pipes] section")

    ep_config = workspace_config["edgar-pipes"]
    if "database" not in ep_config:
        raise RuntimeError(f"{ft_config_path}: Missing required 'database' in [edgar-pipes] section")
    if "journals" not in ep_config:
        raise RuntimeError(f"{ft_config_path}: Missing required 'journals' in [edgar-pipes] section")

    # Workspace root is the directory containing ft.toml
    workspace_root = ft_config_path.parent

    return workspace_root, workspace_config


def get_db_path(workspace_root: Path, workspace_config: dict[str, Any]) -> Path:
    """
    Get database file path from workspace configuration.

    Args:
        workspace_root: Directory containing ft.toml
        workspace_config: Loaded workspace configuration

    Returns:
        Absolute path to database file
    """
    db_path = workspace_config["edgar-pipes"]["database"]
    return (workspace_root / db_path).resolve()


def get_journal_path(workspace_root: Path, workspace_config: dict[str, Any], journal_name: str = "default") -> Path:
    """
    Get journal file path from workspace configuration.

    Args:
        workspace_root: Directory containing ft.toml
        workspace_config: Loaded workspace configuration
        journal_name: Journal name (e.g., "default", "setup", "daily")

    Returns:
        Absolute path to journal file
    """
    journals_dir = workspace_config["edgar-pipes"]["journals"]
    journals_path = (workspace_root / journals_dir).resolve()
    return journals_path / f"{journal_name}.jsonl"


def get_default_ticker(workspace_config: dict[str, Any]) -> str | None:
    """
    Get default ticker from workspace configuration if specified.

    Args:
        workspace_config: Loaded workspace configuration

    Returns:
        Default ticker string or None if not specified
    """
    if "workspace" in workspace_config:
        return workspace_config["workspace"].get("ticker")
    return None


def get_history_path() -> Path:
    """
    Get system-level history file path (ephemeral, in tmp).
    Uses UID for multi-user safety.
    """
    import tempfile

    # Prefer XDG_RUNTIME_DIR (user-specific, secure)
    runtime_dir = os.environ.get('XDG_RUNTIME_DIR')
    if runtime_dir:
        return Path(runtime_dir) / 'edgar-pipes-history.jsonl'

    # Fallback to tmp with UID for multi-user safety
    uid = os.getuid()
    return Path(tempfile.gettempdir()) / f'edgar-pipes-{uid}.jsonl'


def get_user_agent(config: dict) -> str:
    """Get user agent for EDGAR API requests."""
    return config["edgar"]["user_agent"]


def get_theme(config: dict) -> str:
    """Get the configured theme name."""
    return config["output"]["theme"]
