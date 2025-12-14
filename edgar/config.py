"""Configuration management for edgar-pipes.

All configuration is now in a single ep.toml file at the workspace root.
This file contains:
- User preferences (user_agent, theme)
- Database and company info (database, ticker, cik, name)
- XBRL schema (roles, concepts, groups, targets)
"""

import os
import re
import sys
import tomllib
from typing import Any, Dict, List, Tuple
from pathlib import Path


DEFAULT_CONFIG = {
    "user_agent": "edgar-pipes",  # Fallback (not ideal, prompt user)
    "theme": "nobox-minimal",
}


def find_toml(start_dir: Path | None = None) -> Path | None:
    """
    Find ep.toml by walking up directory tree from start_dir.

    Args:
        start_dir: Directory to start search from (default: current directory)

    Returns:
        Path to ep.toml file if found, None otherwise
    """
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    # Walk up directory tree
    while True:
        config = current / "ep.toml"
        if config.exists():
            return config

        # Check if we've reached the root
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            return None

        current = parent


def load_toml(workspace: str | None = None) -> tuple[Path, dict[str, Any]]:
    """
    Load workspace configuration from ep.toml file.

    Args:
        workspace: Workspace path from pipeline context (if available)

    Returns:
        Tuple of (root, cfg) - workspace root and configuration dict

    Raises:
        RuntimeError: If no ep.toml file found
    """
    if workspace:
        start_dir = Path(workspace)
    else:
        start_dir = Path.cwd()

    config_path = find_toml(start_dir)

    if config_path is None:
        error_msg = f"""No ep.toml workspace configuration found.

Searched from: {start_dir}

Create an ep.toml file in your workspace directory using 'ep init':

  $ ep init

Or create one manually. See https://github.com/emifrn/edgar-pipes for more information."""
        raise RuntimeError(error_msg)

    # Load the TOML file
    try:
        with open(config_path, "rb") as f:
            cfg = tomllib.load(f)
    except Exception as e:
        raise RuntimeError(f"Error loading {config_path}: {e}")

    required_fields = ["database", "ticker"]
    missing_fields = [field for field in required_fields if field not in cfg]

    if missing_fields:
        raise RuntimeError(
            f"{config_path}: Missing required fields: {', '.join(missing_fields)}\n"
            f"Run 'ep init' to create a valid configuration."
        )

    # Workspace root is the directory containing ep.toml
    root = config_path.parent

    return root, cfg


def get_db_path(root: Path, cfg: dict[str, Any]) -> Path:
    """
    Get database file path from ep.toml configuration.

    Args:
        root: Workspace root directory containing ep.toml
        cfg: Loaded ep.toml configuration

    Returns:
        Absolute path to database file
    """
    db_path = cfg["database"]
    return (root / db_path).resolve()


def get_ticker(cfg: dict[str, Any]) -> str:
    """
    Get ticker from ep.toml configuration.

    Args:
        cfg: Loaded ep.toml configuration

    Returns:
        Ticker string
    """
    return cfg["ticker"]


def get_cik(cfg: dict[str, Any]) -> str:
    """
    Get CIK from ep.toml configuration.

    Args:
        cfg: Loaded ep.toml configuration

    Returns:
        CIK string
    """
    return cfg["cik"]


def get_user_agent(cfg: dict[str, Any]) -> str:
    """
    Get user agent from ep.toml configuration.

    Args:
        cfg: Loaded ep.toml configuration

    Returns:
        User agent string, or default if not specified
    """
    return cfg.get("user_agent", DEFAULT_CONFIG["user_agent"])


def get_theme(cfg: dict[str, Any]) -> str:
    """
    Get theme from ep.toml configuration.

    Args:
        cfg: Loaded ep.toml configuration

    Returns:
        Theme string, or default if not specified
    """
    return cfg.get("theme", DEFAULT_CONFIG["theme"])


# =============================================================================
# Validation Functions
# =============================================================================

def validate(cfg: dict) -> Tuple[List[str], List[str]]:
    """
    Validate ep.toml structure and business rules.

    Args:
        cfg: Loaded ep.toml configuration

    Returns:
        (errors, warnings) tuple where errors are fatal, warnings are not
    """
    errors = []
    warnings = []

    # Run all validations
    errors.extend(_validate_uids(cfg))
    errors.extend(_validate_references(cfg))
    errors.extend(_validate_patterns(cfg))
    warnings.extend(_check_unused(cfg))
    return errors, warnings


def _validate_uids(cfg: dict) -> List[str]:
    """Check UID uniqueness."""
    errors = []
    concepts = cfg.get("concepts", {})
    uid_to_concepts: Dict[int, List[str]] = {}

    for concept_name, concept_def in concepts.items():
        if "uid" not in concept_def:
            errors.append(f"Concept '{concept_name}' missing required 'uid' field")
            continue

        uid = concept_def["uid"]
        if uid not in uid_to_concepts:
            uid_to_concepts[uid] = []
        uid_to_concepts[uid].append(concept_name)

    for uid, concept_names in uid_to_concepts.items():
        if len(concept_names) > 1:
            errors.append(
                f"Duplicate UID {uid} used by concepts: {', '.join(concept_names)}"
            )

    return errors


def _validate_references(cfg: dict) -> List[str]:
    """Check that all references (roles, concepts, groups) exist."""
    errors = []
    concepts = cfg.get("concepts", {})
    groups = cfg.get("groups", {})
    roles = cfg.get("roles", {})

    all_concept_uids = set(c.get("uid") for c in concepts.values() if "uid" in c)
    all_group_names = set(groups.keys())

    # Validate group references
    for group_name, group_def in groups.items():
        # Check 'from' reference if present
        from_group = group_def.get("from")
        if from_group:
            if from_group not in groups:
                errors.append(f"Group '{group_name}' references undefined parent group '{from_group}'")
                continue  # Skip further validation for this group

        # Check role reference (required unless 'from' is set)
        if "role" not in group_def and not from_group:
            errors.append(f"Group '{group_name}' missing required 'role' field (required when 'from' is not set)")
            continue

        # If role is specified, validate it exists
        if "role" in group_def:
            role_ref = group_def["role"]
            if role_ref not in roles:
                errors.append(
                    f"Group '{group_name}' references undefined role '{role_ref}'"
                )

        # Check concept UIDs
        if "concepts" not in group_def:
            errors.append(f"Group '{group_name}' missing required 'concepts' field")
            continue

        group_concepts = set(group_def["concepts"])
        invalid_uids = group_concepts - all_concept_uids
        if invalid_uids:
            errors.append(
                f"Group '{group_name}' references undefined concept UIDs: {sorted(invalid_uids)}"
            )

        # If derived from another group, validate concepts are subset of parent
        if from_group and from_group in groups:
            parent_concepts = set(groups[from_group].get("concepts", []))
            invalid_concepts = group_concepts - parent_concepts
            if invalid_concepts:
                errors.append(
                    f"Group '{group_name}' contains concepts not in parent group '{from_group}': {sorted(invalid_concepts)}"
                )

    return errors


def _validate_patterns(cfg: dict) -> List[str]:
    """Check that all regex patterns are valid."""
    errors = []
    roles = cfg.get("roles", {})
    concepts = cfg.get("concepts", {})

    for role_name, role_def in roles.items():
        if "pattern" not in role_def:
            errors.append(f"Role '{role_name}' missing required 'pattern' field")
            continue

        try:
            re.compile(role_def["pattern"])
        except re.error as e:
            errors.append(f"Role '{role_name}' has invalid regex pattern: {e}")

    for concept_name, concept_def in concepts.items():
        if "pattern" not in concept_def:
            errors.append(f"Concept '{concept_name}' missing required 'pattern' field")
            continue

        try:
            re.compile(concept_def["pattern"])
        except re.error as e:
            errors.append(f"Concept '{concept_name}' has invalid regex pattern: {e}")

    return errors


def _check_unused(cfg: dict) -> List[str]:
    """Warn about unused definitions."""
    warnings = []
    concepts = cfg.get("concepts", {})
    groups = cfg.get("groups", {})
    roles = cfg.get("roles", {})

    all_concept_uids = set(c.get("uid") for c in concepts.values() if "uid" in c)
    used_concept_uids = set()
    for group_def in groups.values():
        if "concepts" in group_def:
            used_concept_uids.update(group_def["concepts"])

    unused_uids = all_concept_uids - used_concept_uids
    if unused_uids:
        unused_names = [name for name, defn in concepts.items() if defn.get("uid") in unused_uids]
        warnings.append(
            f"Concepts defined but not used in any group: {', '.join(sorted(unused_names))}"
        )

    used_roles = set(g.get("role") for g in groups.values() if "role" in g)
    unused_roles = set(roles.keys()) - used_roles
    if unused_roles:
        warnings.append(
            f"Roles defined but not used in any group: {', '.join(sorted(unused_roles))}"
        )

    return warnings
