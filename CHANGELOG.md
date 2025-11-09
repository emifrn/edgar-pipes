# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-12-XX

Initial release.

### Added
- Progressive discovery workflow for SEC EDGAR XBRL financial data extraction
- CLI commands: `probe`, `select`, `new`, `add`, `update`, `report`, `calc`, `stats`, `modify`, `delete`, `journal`, `history`, `config`
- Pattern-based matching system for roles and concepts
- Hierarchical group organization (Balance, Operations, CashFlow, Equity)
- SQLite database for persistent storage
- Pipeline architecture with Unix pipes support
- Journal system for reproducible workflows
- Multiple output formats (table, CSV, JSON)
- XDG-compliant configuration system
- Optional `--note` field for role and concept patterns to document pattern rationale

### Known Limitations
- US companies only (Form 10-Q/10-K)
- Consolidated facts only (no segment/dimensional data)
- Alpha software - expect rough edges

---

[0.1.0]: https://github.com/emifrn/edgar-pipes/releases/tag/v0.1.0
