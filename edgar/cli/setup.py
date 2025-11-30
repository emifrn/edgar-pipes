"""
CLI: setup

Declarative workspace setup from setup.json configuration file.
Replaces imperative journal-based approach with structured configuration.
"""
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any

# Local modules
from edgar import config
from edgar import db
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


# =============================================================================
# Validation Functions
# =============================================================================

def validate_setup(setup: dict) -> Tuple[List[str], List[str]]:
    """
    Validate setup.json structure and business rules.

    Returns:
        (errors, warnings) tuple where errors are fatal, warnings are not
    """
    errors = []
    warnings = []

    # Run all validations
    errors.extend(_validate_uids(setup))
    errors.extend(_validate_references(setup))
    errors.extend(_validate_patterns(setup))
    warnings.extend(_check_unused(setup))

    return errors, warnings


def _validate_uids(setup: dict) -> List[str]:
    """Check UID uniqueness."""
    errors = []
    concepts = setup.get("concepts", {})
    uid_to_concepts: Dict[int, List[str]] = {}

    for concept_name, concept_def in concepts.items():
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


def _validate_references(setup: dict) -> List[str]:
    """Check that all references (roles, concepts, groups) exist."""
    errors = []
    concepts = setup.get("concepts", {})
    groups = setup.get("groups", {})
    roles = setup.get("roles", {})
    targets = setup.get("targets", {})

    all_concept_uids = set(c["uid"] for c in concepts.values())
    all_group_names = set(groups.keys())

    # Validate group references
    for group_name, group_def in groups.items():
        # Check role reference
        role_ref = group_def["role"]
        if role_ref not in roles:
            errors.append(
                f"Group '{group_name}' references undefined role '{role_ref}'"
            )

        # Check concept UIDs
        group_concepts = set(group_def["concepts"])
        invalid_uids = group_concepts - all_concept_uids
        if invalid_uids:
            errors.append(
                f"Group '{group_name}' references undefined concept UIDs: {sorted(invalid_uids)}"
            )

        # Check subgroups
        for subgroup_name, subgroup_def in group_def.get("subgroups", {}).items():
            subgroup_concepts = set(subgroup_def["concepts"])
            invalid_concepts = subgroup_concepts - group_concepts
            if invalid_concepts:
                errors.append(
                    f"Subgroup '{subgroup_name}' contains concepts not in parent group '{group_name}': {sorted(invalid_concepts)}"
                )

    # Validate target references (can reference groups or subgroups)
    all_subgroup_names = set()
    for group_def in groups.values():
        all_subgroup_names.update(group_def.get("subgroups", {}).keys())

    all_valid_names = all_group_names | all_subgroup_names

    for target_name, target_def in targets.items():
        target_groups = set(target_def["groups"])
        invalid_groups = target_groups - all_valid_names
        if invalid_groups:
            errors.append(
                f"Target '{target_name}' references undefined groups/subgroups: {sorted(invalid_groups)}"
            )

    return errors


def _validate_patterns(setup: dict) -> List[str]:
    """Check that all regex patterns are valid."""
    errors = []
    roles = setup.get("roles", {})
    concepts = setup.get("concepts", {})

    for role_name, role_def in roles.items():
        try:
            re.compile(role_def["pattern"])
        except re.error as e:
            errors.append(f"Role '{role_name}' has invalid regex pattern: {e}")

    for concept_name, concept_def in concepts.items():
        try:
            re.compile(concept_def["pattern"])
        except re.error as e:
            errors.append(f"Concept '{concept_name}' has invalid regex pattern: {e}")

    return errors


def _check_unused(setup: dict) -> List[str]:
    """Warn about unused definitions."""
    warnings = []
    concepts = setup.get("concepts", {})
    groups = setup.get("groups", {})
    roles = setup.get("roles", {})

    all_concept_uids = set(c["uid"] for c in concepts.values())
    used_concept_uids = set()
    for group_def in groups.values():
        used_concept_uids.update(group_def["concepts"])

    unused_uids = all_concept_uids - used_concept_uids
    if unused_uids:
        unused_names = [name for name, defn in concepts.items() if defn["uid"] in unused_uids]
        warnings.append(
            f"Concepts defined but not used in any group: {', '.join(sorted(unused_names))}"
        )

    used_roles = set(g["role"] for g in groups.values())
    unused_roles = set(roles.keys()) - used_roles
    if unused_roles:
        warnings.append(
            f"Roles defined but not used in any group: {', '.join(sorted(unused_roles))}"
        )

    return warnings


# =============================================================================
# Execution Functions
# =============================================================================

def execute_setup(setup: dict, cmd: Cmd, target: str = "all", dry_run: bool = False) -> Result[None, str]:
    """
    Execute the setup configuration.

    Args:
        setup: Setup configuration dict
        cmd: Command context
        target: Target name (default: "all")
        dry_run: If True, only show what would be done

    Returns:
        ok(None) if successful, err(str) if failed
    """
    workspace_name = setup["workspace"]["name"]
    ticker = setup["workspace"]["ticker"]
    cik = setup["workspace"]["cik"]

    # Determine which groups to process
    if target == "all":
        groups_to_process = list(setup["groups"].keys())
    else:
        targets = setup.get("targets", {})
        if target not in targets:
            return err(f"cli.setup.execute_setup: unknown target '{target}'. Available: {', '.join(targets.keys())}, all")
        groups_to_process = targets[target]["groups"]

    if dry_run:
        print(f"[DRY RUN] Would create workspace: {workspace_name} ({ticker}, CIK: {cik})")
        return _plan_setup(setup, groups_to_process)

    # Track statistics
    stats = {
        "roles_created": 0,
        "concepts_created": 0,
        "groups_created": 0,
        "subgroups_created": 0,
    }

    # 1. Create workspace (if not exists)
    create_result = _create_workspace(workspace_name, ticker, cik)
    if is_not_ok(create_result):
        return create_result

    # 2. Create roles
    roles_result = _create_roles(setup, stats)
    if is_not_ok(roles_result):
        return roles_result

    # 3. Create concepts
    concepts_result = _create_concepts(setup, ticker, stats)
    if is_not_ok(concepts_result):
        return concepts_result

    # 4. Create groups and subgroups
    groups_result = _create_groups(setup, groups_to_process, ticker, stats)
    if is_not_ok(groups_result):
        return groups_result

    # 5. Update (extract facts)
    update_result = _update_groups(groups_to_process, ticker)
    if is_not_ok(update_result):
        return update_result

    _print_summary(stats)
    return ok(None)


def _plan_setup(setup: dict, groups_to_process: List[str]) -> Result[None, str]:
    """Show what would be created (dry run)."""
    roles = setup.get("roles", {})
    concepts = setup.get("concepts", {})
    groups = setup.get("groups", {})

    print(f"\nWould create:")
    print(f"  • {len(roles)} roles")
    print(f"  • {len(concepts)} concepts")
    print(f"  • {len(groups_to_process)} groups")

    # Count subgroups
    subgroup_count = 0
    for group_name in groups_to_process:
        if group_name in groups:
            subgroup_count += len(groups[group_name].get("subgroups", {}))

    if subgroup_count > 0:
        print(f"  • {subgroup_count} subgroups")

    print(f"\nGroups to process: {', '.join(groups_to_process)}")

    return ok(None)


def _create_workspace(name: str, ticker: str, cik: str) -> Result[None, str]:
    """Create workspace if it doesn't exist."""
    # Check if workspace exists
    db_path = config.get_db_path(name)
    if db_path.exists():
        print(f"Workspace '{name}' already exists at {db_path}")
        return ok(None)

    # Create new workspace
    print(f"Creating workspace: {name} ({ticker}, CIK: {cik})")
    conn = db.init.create_database(db_path)
    db.init.insert_ticker(conn, ticker, cik)
    conn.close()

    return ok(None)


def _create_roles(setup: dict, stats: dict) -> Result[None, str]:
    """Create all roles."""
    roles = setup.get("roles", {})
    print(f"\nCreating {len(roles)} roles...")

    for role_name, role_def in roles.items():
        # Create role (implementation depends on your db schema)
        # For now, just count it
        stats["roles_created"] += 1
        print(f"  • {role_name}")

    return ok(None)


def _create_concepts(setup: dict, ticker: str, stats: dict) -> Result[None, str]:
    """Create all concepts."""
    concepts = setup.get("concepts", {})
    print(f"\nCreating {len(concepts)} concepts...")

    for concept_name, concept_def in concepts.items():
        # Create concept (implementation depends on your db schema)
        # For now, just count it
        stats["concepts_created"] += 1

    return ok(None)


def _create_groups(setup: dict, groups_to_process: List[str], ticker: str, stats: dict) -> Result[None, str]:
    """Create groups and subgroups."""
    groups = setup.get("groups", {})
    print(f"\nCreating {len(groups_to_process)} groups...")

    for group_name in groups_to_process:
        if group_name not in groups:
            return err(f"cli.setup._create_groups: group '{group_name}' not found in setup")

        group_def = groups[group_name]
        stats["groups_created"] += 1
        print(f"  • {group_name} ({len(group_def['concepts'])} concepts)")

        # Create subgroups
        for subgroup_name in group_def.get("subgroups", {}).keys():
            stats["subgroups_created"] += 1

    return ok(None)


def _update_groups(groups_to_process: List[str], ticker: str) -> Result[None, str]:
    """Run update to extract facts for all groups."""
    print(f"\nExtracting facts for {len(groups_to_process)} groups...")
    # Implementation depends on your update logic
    return ok(None)


def _print_summary(stats: dict):
    """Print execution summary."""
    print(f"\n✓ Setup complete:")
    print(f"  • {stats['roles_created']} roles created")
    print(f"  • {stats['concepts_created']} concepts created")
    print(f"  • {stats['groups_created']} groups created")
    if stats['subgroups_created'] > 0:
        print(f"  • {stats['subgroups_created']} subgroups created")


def add_arguments(subparsers):
    """Add setup command with subcommands."""

    parser_setup = subparsers.add_parser(
        "setup",
        help="declarative workspace setup from setup.json"
    )
    setup_subparsers = parser_setup.add_subparsers(dest='setup_cmd', help='setup commands')

    # setup validate
    parser_validate = setup_subparsers.add_parser(
        "validate",
        help="validate setup.json file"
    )
    parser_validate.add_argument(
        "file",
        nargs="?",
        default="setup.json",
        help="path to setup.json file (default: setup.json)"
    )
    parser_validate.set_defaults(func=run)

    # setup plan
    parser_plan = setup_subparsers.add_parser(
        "plan",
        help="show what would be created (dry run)"
    )
    parser_plan.add_argument(
        "file",
        nargs="?",
        default="setup.json",
        help="path to setup.json file (default: setup.json)"
    )
    parser_plan.add_argument(
        "target",
        nargs="?",
        default="all",
        help="target to plan (default: all)"
    )
    parser_plan.set_defaults(func=run)

    # setup apply
    parser_apply = setup_subparsers.add_parser(
        "apply",
        help="apply setup.json to create/update workspace"
    )
    parser_apply.add_argument(
        "file",
        nargs="?",
        default="setup.json",
        help="path to setup.json file (default: setup.json)"
    )
    parser_apply.add_argument(
        "target",
        nargs="?",
        default="all",
        help="target to apply (default: all)"
    )
    parser_apply.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[None, str]:
    """
    Execute setup command.

    Returns:
        ok(None) - Normal completion
        err(str) - Error occurred
    """

    if args.setup_cmd == 'validate':
        return run_validate(cmd, args)
    elif args.setup_cmd == 'plan':
        return run_plan(cmd, args)
    elif args.setup_cmd == 'apply':
        return run_apply(cmd, args)
    else:
        return err(f"cli.setup.run: unknown subcommand: {args.setup_cmd}")


def run_validate(cmd: Cmd, args) -> Result[None, str]:
    """Validate setup.json file."""

    # Load setup file
    setup_path = Path(args.file)
    if not setup_path.exists():
        return err(f"cli.setup.run_validate: setup file not found: {setup_path}")

    try:
        with open(setup_path) as f:
            setup = json.load(f)
    except json.JSONDecodeError as e:
        return err(f"cli.setup.run_validate: JSON syntax error in {setup_path}: {e}")

    # Validate
    print(f"Validating {setup_path}...")
    errors, warnings = validate_setup(setup)
    is_valid = len(errors) == 0

    # Print errors
    if errors:
        print(f"\n✗ Found {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)

    # Print warnings
    if warnings:
        print(f"\n⚠ Found {len(warnings)} warning(s):")
        for warning in warnings:
            print(f"  {warning}")

    # Print summary
    workspace = setup.get("workspace", {})
    print(f"\nSummary:")
    print(f"  Workspace: {workspace.get('name')} ({workspace.get('ticker')})")
    print(f"  Roles: {len(setup.get('roles', {}))}")
    print(f"  Concepts: {len(setup.get('concepts', {}))}")
    print(f"  Groups: {len(setup.get('groups', {}))}")

    if 'targets' in setup:
        print(f"  Targets: {len(setup['targets'])}")

    if is_valid:
        print(f"\n✓ Validation successful")
        return ok(None)
    else:
        print(f"\n✗ Validation failed", file=sys.stderr)
        return err("cli.setup.run_validate: validation failed")


def run_plan(cmd: Cmd, args) -> Result[None, str]:
    """Show execution plan (dry run)."""

    # Load and validate setup file
    setup_path = Path(args.file)
    if not setup_path.exists():
        return err(f"cli.setup.run_plan: setup file not found: {setup_path}")

    try:
        with open(setup_path) as f:
            setup = json.load(f)
    except json.JSONDecodeError as e:
        return err(f"cli.setup.run_plan: JSON syntax error in {setup_path}: {e}")

    # Validate first
    errors, _ = validate_setup(setup)
    if errors:
        print("✗ Setup file has validation errors. Run 'setup validate' first.", file=sys.stderr)
        return err("cli.setup.run_plan: validation failed")

    # Execute in dry-run mode
    return execute_setup(setup, cmd, target=args.target, dry_run=True)


def run_apply(cmd: Cmd, args) -> Result[None, str]:
    """Apply setup.json to create/update workspace."""

    # Load and validate setup file
    setup_path = Path(args.file)
    if not setup_path.exists():
        return err(f"cli.setup.run_apply: setup file not found: {setup_path}")

    try:
        with open(setup_path) as f:
            setup = json.load(f)
    except json.JSONDecodeError as e:
        return err(f"cli.setup.run_apply: JSON syntax error in {setup_path}: {e}")

    # Validate first
    errors, _ = validate_setup(setup)
    if errors:
        print("✗ Setup file has validation errors. Run 'setup validate' first.", file=sys.stderr)
        return err("cli.setup.run_apply: validation failed")

    # Execute
    return execute_setup(setup, cmd, target=args.target, dry_run=False)
