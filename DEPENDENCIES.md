# Dependencies

## Overview

edgar-pipes has minimal dependencies, relying on Python's standard library and
Arelle for XBRL parsing.

## Requirements

- **Python 3.11+** - For built-in TOML support (`tomllib`)
- **Arelle** - XBRL parsing library
  - Source: https://github.com/Arelle/Arelle (installed from GitHub, not PyPI)
  - License: Apache 2.0

## Installation

All dependencies are automatically installed:

```bash
git clone https://github.com/emifrn/edgar-pipes.git
cd edgar-pipes
pip install -e .
```

## Standard Library Usage

edgar-pipes uses only Python standard library for all other functionality:
- `sqlite3` - Database storage
- `argparse` - CLI parsing
- `tomllib` - Configuration (Python 3.11+)
- `pathlib`, `json`, `datetime`, `re`, `urllib` - Core utilities

## Arelle Dependencies

Arelle brings its own dependencies (automatically managed by pip):
- `lxml` - XML parsing
- `isodate`, `python-dateutil` - Date handling
- `numpy` - Numerical operations
- Various others for XBRL processing

See `pip list` after installation for complete list.

## Why Arelle from GitHub?

The GitHub version has the latest XBRL parsing improvements and bug fixes,
often ahead of PyPI releases.

## Updating

### Update edgar-pipes
```bash
cd edgar-pipes
git pull origin main
```
Changes are immediately available in editable mode - no reinstall needed.

### Update Arelle
```bash
pip install --upgrade --force-reinstall "arelle-release @ git+https://github.com/Arelle/Arelle.git@master"
```

## Troubleshooting

### Python version too old
```bash
python --version  # Must be 3.11+
```

### Arelle installation fails
If GitHub access fails, use PyPI as fallback (may be outdated):
```bash
pip install arelle-release
```

## License Compatibility

- edgar-pipes: MIT
- Arelle: Apache 2.0
- All licenses are compatible
