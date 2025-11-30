"""
CLI: init

Interactive workspace initialization. Creates ep.toml configuration file.
"""
import sys
import sqlite3
from pathlib import Path

# Local modules
from edgar import config
from edgar import db
from edgar import cache
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_not_ok


EP_TOML_TEMPLATE = """# Edgar Pipes Configuration
# Company: {name}

# User preferences
user_agent = "{user_agent}"
theme = "nobox-minimal"

# Database and company identification
database = "{database}"
ticker = "{ticker}"
cik = "{cik}"
name = "{name}"

# Data extraction configuration
# cutoff = "2015-01-01"  # Optional: only fetch filings after this date (defaults to 10 years ago)

# =============================================================================
# XBRL Roles - Define where to find data in filings
# =============================================================================

[roles.balance]
pattern = "(?i)^(CONDENSED)?CONSOLIDATEDBALANCESHEETS(Unaudited)?(Parenthetical)?$"
note = "Balance sheet statement"

[roles.operations]
pattern = "(?i)^(CONDENSED)?CONSOLIDATEDSTATEMENTSOFINCOME(Unaudited)?(Parenthetical)?$"
note = "Income statement"

[roles.cashflow]
pattern = "(?i)^(CONDENSED)?CONSOLIDATEDSTATEMENTSOFCASHFLOWS(Unaudited)?$"
note = "Cash flow statement"

[roles.equity]
pattern = "(?i)^(CONDENSED)?CONSOLIDATEDSTATEMENTSOFSTOCKHOLDERSEQUITY(Unaudited)?(Parenthetical)?$"
note = "Equity statement"

# =============================================================================
# Concepts - Financial metrics to extract
# =============================================================================

# Example concepts - customize for your company
[concepts.Cash]
uid = 1
pattern = "^CashAndCashEquivalentsAtCarryingValue$"
note = "Cash and cash equivalents"

[concepts.Revenue]
uid = 100
pattern = "^(RevenueFromContractWithCustomerExcludingAssessedTax|SalesRevenueNet)$"
note = "Total revenue"

# =============================================================================
# Groups - Organize concepts for extraction and reporting
# =============================================================================

[groups.Balance]
role = "balance"
concepts = [1]

[groups.Operations]
role = "operations"
concepts = [100]
"""


def add_arguments(subparsers):
    """Add init command to argument parser."""
    parser_init = subparsers.add_parser(
        "init",
        help="initialize workspace with ep.toml configuration"
    )
    parser_init.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing ep.toml file"
    )
    parser_init.add_argument(
        "--ua",
        metavar="USER_AGENT",
        help="user agent for SEC API (e.g., 'John Doe john@example.com')"
    )
    parser_init.add_argument(
        "--ticker",
        metavar="TICKER",
        help="company ticker symbol (e.g., AAPL)"
    )
    parser_init.add_argument(
        "--db",
        metavar="PATH",
        default="db/edgar.db",
        help="database path relative to ep.toml (default: db/edgar.db)"
    )
    parser_init.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[None, str]:
    """
    Initialize workspace with ep.toml configuration.

    If ep.toml doesn't exist, run interactive setup and create template.
    If ep.toml exists, show status (unless --force).

    Returns:
        ok(None) - Normal completion
        err(str) - Error occurred
    """
    ep_toml_path = Path.cwd() / "ep.toml"

    # Check if ep.toml already exists
    if ep_toml_path.exists() and not args.force:
        return show_status(ep_toml_path)

    # Determine if running in interactive or non-interactive mode
    non_interactive = args.ua and args.ticker

    # Interactive setup
    if args.force:
        print("Creating new ep.toml configuration (--force)...\n")
    elif not non_interactive:
        print("Welcome to edgar-pipes!\n")
        print("This will create an ep.toml configuration file in the current directory.\n")

    # Gather user input (use args if provided, otherwise prompt)
    user_agent = args.ua if args.ua else prompt_user_agent()
    ticker = args.ticker.upper() if args.ticker else prompt_required("Company ticker (e.g., AAPL): ").upper()
    database = args.db  # Has default, always available

    # Resolve database path
    db_path = (Path.cwd() / database).resolve()

    # Create database directory if needed
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize database and fetch company info from SEC
    if not non_interactive:
        print(f"\nInitializing database: {db_path}")
        print(f"Fetching company information from SEC for {ticker}...")
    else:
        print(f"Initializing database: {db_path}")
        print(f"Fetching company information from SEC for {ticker}...")

    try:
        # Connect and initialize database schema
        conn = sqlite3.connect(db_path)
        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return err(f"cli.init.run: failed to initialize database: {result[1]}")

        # Fetch and cache company entity from SEC
        result = cache.resolve_entities(conn, user_agent, [ticker])
        if is_not_ok(result):
            conn.close()
            return err(f"cli.init.run: failed to fetch company from SEC: {result[1]}")

        entities = result[1]
        if not entities:
            conn.close()
            return err(f"cli.init.run: ticker '{ticker}' not found in SEC database")

        entity = entities[0]
        cik = entity["cik"]
        name = entity["name"]
        ticker = entity["ticker"].upper()

        conn.commit()
        conn.close()

        print(f"✓ Found company: {name} (CIK: {cik})")

    except Exception as e:
        return err(f"cli.init.run: database error: {e}")

    # Create ep.toml from template
    ep_toml_content = EP_TOML_TEMPLATE.format(
        user_agent=user_agent,
        ticker=ticker,
        cik=cik,
        name=name,
        database=database,
    )

    try:
        with open(ep_toml_path, "w") as f:
            f.write(ep_toml_content)
    except Exception as e:
        return err(f"cli.init.run: failed to write ep.toml: {e}")

    print(f"✓ Created {ep_toml_path}")

    print("\n✓ Workspace initialized successfully!")
    print(f"\nCompany: {name}")
    print(f"Ticker: {ticker}")
    print(f"CIK: {cik}")
    print(f"Database: {db_path}")

    print("\nNext steps:")
    print("  1. Run 'ep probe filings' to fetch SEC filings")
    print("  2. Run 'ep probe concepts' to explore XBRL concepts")
    print("  3. Edit ep.toml to define roles and concepts for your analysis")
    print("  4. Run 'ep build -c' to validate configuration")
    print("  5. Run 'ep build' to extract financial data")

    return ok(None)


def show_status(ep_toml_path: Path) -> Result[None, str]:
    """Show status of existing workspace."""
    print(f"Workspace already initialized: {ep_toml_path}\n")

    # Try to load and show basic info
    try:
        workspace_root, ep_config = config.load_toml()

        print("Configuration:")
        print(f"  Ticker: {config.get_ticker(ep_config)}")
        print(f"  CIK: {config.get_cik(ep_config)}")
        print(f"  Database: {ep_config.get('database', 'not set')}")

        # Count schema elements
        num_roles = len(ep_config.get("roles", {}))
        num_concepts = len(ep_config.get("concepts", {}))
        num_groups = len(ep_config.get("groups", {}))

        print(f"\nSchema:")
        print(f"  Roles: {num_roles}")
        print(f"  Concepts: {num_concepts}")
        print(f"  Groups: {num_groups}")

        print(f"\nUse 'ep build -c' to validate configuration")
        print(f"Use 'ep build' to create/update database")
        print(f"Use 'ep init --force' to recreate ep.toml")

    except Exception as e:
        print(f"Warning: Could not load ep.toml: {e}", file=sys.stderr)
        return err("cli.init.show_status: invalid ep.toml")

    return ok(None)


def prompt_user_agent() -> str:
    """Prompt for user agent (required by SEC)."""
    print("The SEC requires a user-agent for API requests.")
    while True:
        user_agent = input('Your name and email (e.g., "John Doe john@example.com"): ').strip()
        if user_agent:
            return user_agent
        print("User-agent is required. Please try again.")


def prompt_required(prompt: str) -> str:
    """Prompt for required input."""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("This field is required. Please try again.")


def prompt_optional(prompt: str, default: str) -> str:
    """Prompt for optional input with default value."""
    value = input(f"{prompt}[{default}] ").strip()
    return value if value else default
