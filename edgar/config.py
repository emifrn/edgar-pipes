"""Configuration management for edgar-pipes.

Loads configuration with the following precedence (highest to lowest):
1. Environment variables (EDGAR_PIPES_*)
2. Config file (~/.config/edgar-pipes/config.toml)
3. Built-in defaults
"""

import os
import sys
import tomllib
from typing import Any
from pathlib import Path


DEFAULT_CONFIG = {
    "edgar": {
        "user_agent": "edgar-pipes/0.1.0",  # Fallback (not ideal, prompt user)
    },
    "database": {
        "path": "~/.local/share/edgar-pipes/store.db",
    },
    "journal": {
        "path": "~/.local/share/edgar-pipes/journals",
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
    1. Environment variables (highest)
    2. Config file (~/.config/edgar-pipes/config.toml)
    3. Built-in defaults (lowest)
    """
    # Start with defaults
    config = {
        "edgar": DEFAULT_CONFIG["edgar"].copy(),
        "database": DEFAULT_CONFIG["database"].copy(),
        "journal": DEFAULT_CONFIG["journal"].copy(),
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

    # 2. Override with environment variables
    env_overrides = {
        "EDGAR_PIPES_USER_AGENT": ("edgar", "user_agent"),
        "EDGAR_PIPES_DB_PATH": ("database", "path"),
        "EDGAR_PIPES_JOURNAL_PATH": ("journal", "path"),
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

[database]
# Database file location
path = "~/.local/share/edgar-pipes/store.db"

[journal]
# Journal storage location
path = "~/.local/share/edgar-pipes/journals"

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


def ensure_data_dirs(config: dict) -> None:
    """
    Ensure database and journal directories exist.
    Called once at startup.
    """
    # Create database directory
    db_path = get_database_path(config)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create journal directory
    journal_path = get_journal_path(config)
    journal_path.mkdir(parents=True, exist_ok=True)


def get_user_agent(config: dict) -> str:
    """Get user agent for EDGAR API requests."""
    return config["edgar"]["user_agent"]


def get_database_path(config: dict) -> Path:
    """Get database file path, expanding ~ if needed."""
    path = config["database"]["path"]
    return Path(path).expanduser()


def get_journal_path(config: dict) -> Path:
    """Get journal directory path, expanding ~ if needed."""
    path = config["journal"]["path"]
    return Path(path).expanduser()


def get_theme(config: dict) -> str:
    """Get the configured theme name."""
    return config["output"]["theme"]
