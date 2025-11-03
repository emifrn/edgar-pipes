# Installation Guide

## Quick Install

```bash
git clone https://github.com/emifrn/edgar-pipes.git
cd edgar-pipes
pip install -e .
ep --help
```

## Requirements

- Python 3.11+
- pip
- git

Most systems have these. If not:

```bash
# Ubuntu/Debian
sudo apt install python3.11 python3-pip git

# macOS
brew install python@3.11 git
```

## Platform Support

- Linux, macOS

## Installation Options

### Virtual Environment (Recommended)

```bash
python -m venv edgar-env
source edgar-env/bin/activate
pip install -e .
```

### Regular Install

```bash
pip install .
```

Use `-e` (editable) if you want to modify the code or pull updates.

## Verify Installation

```bash
ep --help
python -c "from arelle import ModelManager; print('✓ Arelle installed')"
```

## Updating

```bash
# Update edgar-pipes (editable mode)
cd edgar-pipes
git pull origin main

# Update Arelle
pip install --upgrade --force-reinstall "arelle-release @ git+https://github.com/Arelle/Arelle.git@master"
```

## Uninstalling

```bash
# Remove packages
pip uninstall edgar-pipes arelle-release

# Remove data (optional)
rm -rf ~/.config/edgar-pipes ~/.local/share/edgar-pipes

# Remove source
rm -rf edgar-pipes
```

## Next Steps

See [README.md](README.md) for Quick Start guide.
