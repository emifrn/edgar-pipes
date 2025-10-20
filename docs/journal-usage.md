# Journal Usage Guide

## Overview

The journal system records your ep commands to create repeatable analysis workflows. Think of it as "command history with intent" - you can replay your analysis steps to reproduce results or apply the same process to different companies.

## Core Concepts

**Journal**: A named file that stores your command history
**Recording**: When enabled, all commands (except meta-commands) are automatically saved
**Replay**: Execute previously recorded commands in sequence

## Journal Management

### Switch Journals

```bash
# Switch to default journal
ep journal use

# Switch to named journal (creates if doesn't exist)
ep journal use aeo
ep journal use retail-analysis
```

**Note:** Journal names are independent from recording state. Switching journals doesn't change whether recording is on or off.

### List Available Journals

```bash
ep journal list
```

Shows:
- Journal directory location
- All available journals
- Which one is currently active

### Check Current Status

```bash
# Brief status
ep journal status

# Detailed status with directory
ep journal current
```

## Recording Control

### Enable Recording

```bash
ep journal on
```

Starts recording commands to the current journal. If already enabled, shows "already enabled" message.

**Idempotent:** Safe to run multiple times.

### Disable Recording

```bash
ep journal off
```

Stops recording commands. If already disabled, shows "already disabled" message.

**Idempotent:** Safe to run multiple times.

### Check Recording State

```bash
ep journal status
```

Shows:
- Current journal name
- Recording state: "enabled (on)" or "disabled (off)"

## Typical Workflow

### Initial Setup (Record Once)

```bash
# Create and activate journal for company
ep journal use aeo
ep journal on

# Perform setup commands (these will be recorded)
ep add -t AEO
ep probe filings -t AEO
ep select filings -t AEO | ep probe roles
ep new group Balance
# ... more setup commands ...

# Disable recording when setup is complete
ep journal off
```

### Daily Usage (Recording Off)

```bash
# Ensure recording is off for routine queries
ep journal status  # Check state
ep journal off     # Disable if needed

# Run routine reports (not recorded)
ep report -t AEO -g Balance
ep report -t AEO -g Operations | calc "Margin = Net income / Revenue"
```

### Adding New Features (Recording On)

```bash
# Re-enable recording when adding new concepts/groups
ep journal on

# New setup commands (will be recorded)
ep new concept -t AEO -u 54 -n 'New metric' -p '^SomeTag$'
ep add concept -g Balance -t AEO -u 54

# Disable when done
ep journal off
```

## Command History

### View Recent Commands

```bash
ep history
ep history --limit 50
ep history aeo  # From specific journal
```

### Filter History

```bash
# Only successful commands
ep history --success

# Only errors
ep history --errors

# Pattern matching
ep history --pattern "new concept"
ep history --pattern "probe.*AEO"
```

## Replay

### Replay Entire Journal

```bash
ep journal replay
ep journal replay aeo  # From specific journal
```

### Replay Specific Commands

```bash
# Single command
ep journal replay 5

# Range
ep journal replay 1:10

# Multiple ranges/indices
ep journal replay 1:5,10,15:20

# From specific journal
ep journal replay aeo[1:10]
```

### Replay Modes

**Strict mode** (default for explicit indices):
- Fails if any command is missing or marked as ERROR
- Use for precise replay of known-good sequences

**Lenient mode** (automatic for single ranges like `1:50`):
- Skips missing or ERROR commands with warnings
- Continues with remaining valid commands
- Use for exploratory replay of large ranges

## Best Practices

### When to Enable Recording

✅ **Enable for:**
- Initial company setup
- Adding new groups
- Creating concept patterns
- Defining role patterns
- Building repeatable workflows

❌ **Disable for:**
- Daily report generation
- Exploratory queries
- Testing commands
- Debugging
- One-off calculations

### Journal Organization

**Per-company journals:**
```bash
ep journal use aeo
ep journal use nike
ep journal use walmart
```

**Per-analysis journals:**
```bash
ep journal use retail-setup
ep journal use margin-analysis
```

**Default journal:**
```bash
ep journal use  # For general/temporary work
```

### Workflow Pattern

```bash
# 1. Check state before starting
ep journal status

# 2. Enable recording for setup
ep journal on

# 3. Do your setup work
ep new group MyAnalysis
# ...

# 4. Disable when done
ep journal off

# 5. Verify recording is off
ep journal status
```

### Avoiding Common Mistakes

**Don't:** Toggle blindly
```bash
ep journal silent  # OLD: Don't use this anymore!
```

**Do:** Be explicit about intent
```bash
ep journal status  # Check first
ep journal off     # Then set desired state
```

**Don't:** Leave recording on for daily use
```bash
ep journal on
# ... generate reports for weeks ...
# Journal fills with routine queries
```

**Do:** Enable only when needed
```bash
ep journal on
# Setup commands
ep journal off
# Routine work
```

## Recording Internals

### What Gets Recorded

✅ **Recorded:**
- All data commands: `probe`, `select`, `new`, `add`, `update`, `report`
- Pipeline commands: `cmd1 | cmd2`
- Status indicator: ✓ (success) or ✗ (error)
- Timestamp: Date and time

❌ **Not recorded:**
- `journal use`, `journal list`, `journal current`, `journal status`
- `history` commands
- Meta/inspection commands

### Journal File Format

```
Index  Date        Time      Status  │  Command
  1    2025-10-17  14:06:17  ✓       │  new group Equity
  2    2025-10-17  14:06:27  ✓       │  new role -t AEO -u 3 -p '^Pattern$'
  3    2025-10-17  14:06:34  ✓       │  add role -t AEO -g Equity -u 3
```

### Storage Location

Default: `~/.config/edgar-pipes/`

Override with environment variable:
```bash
export EDGAR_PIPES_JOURNAL_HOME=/path/to/journals
```

Files:
- `journal.txt` - Default journal
- `journal-aeo.txt` - Named journal "aeo"
- `current.txt` - Active journal name
- `silence` - Recording state (file exists = recording disabled)

## Troubleshooting

### "Journal recording already enabled"

You tried to enable recording when it's already on. This is safe - just informational. Check with `ep journal status`.

### Commands not being recorded

Check:
1. `ep journal status` - Is recording enabled?
2. `ep journal current` - Are you using the right journal?
3. Is the command a meta-command that's intentionally not recorded?

### Replay fails partway through

**Strict mode failure:** One command had an error. Check journal with `ep history --errors` to find the problematic command.

**Lenient mode:** Use single range syntax `1:50` to skip errors automatically.

### Wrong journal is active

```bash
ep journal list     # See all journals
ep journal use aeo  # Switch to correct one
```

## Quick Reference

```bash
# Journal management
ep journal use [NAME]   # Switch journal (default if no name)
ep journal list         # List all journals
ep journal current      # Show current journal and directory
ep journal status       # Show current journal and recording state

# Recording control
ep journal on           # Enable recording
ep journal off          # Disable recording

# History and replay
ep history              # View recent commands
ep journal replay       # Replay entire current journal
ep journal replay N     # Replay command N
ep journal replay N:M   # Replay commands N through M
```

## Examples

### Setup New Company

```bash
ep journal use walmart
ep journal on

ep add -t WMT
ep probe filings -t WMT
ep select filings -t WMT | ep probe roles

# ... setup Balance, Operations, Equity groups ...

ep journal off
```

### Apply Existing Pattern to New Company

```bash
# Replay successful setup from one company
ep journal use aeo
ep journal replay 1:50 > /tmp/commands.txt

# Edit commands.txt to replace "AEO" with "WMT"
# Then execute manually or create script
```

### Debug a Failed Setup

```bash
ep history --errors
# Find failed command at index 23

ep history --pattern "concept.*23"
# See context around that command

# Fix and re-run
ep journal on
ep new concept -t AEO -u 23 -n 'Fixed name' -p '^CorrectPattern$'
ep journal off
```

---

**Remember:** The journal system is designed to make your analysis reproducible. Enable recording when building workflows, disable it for daily use.
