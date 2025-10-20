# Edgar CLI Defaults System

## Overview

Implement session-based defaults for high-frequency arguments to reduce repetitive typing during focused work periods.

## Core Commands

```bash
# Set defaults
ep set -t aeo -g Balance
ep set -t msft            # Partial defaults

# Clear defaults  
ep clear -t -g            # Clear specific defaults
ep clear                  # Clear all defaults

# Show current defaults
ep defaults               # Display active defaults
```

## Fallback Resolution Hierarchy

1. **Explicit arguments** (highest priority)
2. **Pipeline data** (context-aware)
3. **Stored defaults** (convenience fallback)

## Implementation Structure

### Storage Location

- `~/.config/edgar/defaults.json` (follows journal pattern)
- JSON format: `{"ticker": "aeo", "group": "Balance"}`

### Core Functions

```python
# cli/defaults.py
def get_defaults() -> dict[str, str]
def set_defaults(**kwargs) -> None  
def clear_defaults(*keys) -> None
def resolve_with_defaults(args, cmd_data, defaults) -> dict

# Integration in commands
def enhance_args_with_defaults(args, cmd_data):
    defaults = get_defaults()
    return resolve_with_defaults(args, cmd_data, defaults)
```

### Applicable Arguments

- `-t/--ticker` (most valuable)
- `-g/--group` (high value for pattern work)
- `-a/--access` (limited value - filing-specific)

## User Experience

**Workflow example:**

```bash
# Set working context
ep set -t aeo -g Balance

# Commands now work without repetition
ep select concepts -p "Asset"           # Uses aeo + Balance
ep select patterns --type concepts      # Uses aeo + Balance  
ep new "Current Assets" --from Balance  # Uses aeo

# Override when needed
ep select concepts -t msft -p "Revenue" # Explicit override

# Clean up
ep clear
```

## Integration Points

- Early resolution in each command's `run()` function
- Shared utility function for consistent behavior
- Optional stderr feedback when defaults are applied
- No changes to core business logic - purely argument enhancement

## Benefits

- **Reduced typing** during focused sessions
- **Maintains explicitness** when needed
- **Consistent with Edgar patterns** (file-based config like journals)
- **Granular control** over which defaults to set/clear
- **Non-intrusive** - doesn't change existing behavior