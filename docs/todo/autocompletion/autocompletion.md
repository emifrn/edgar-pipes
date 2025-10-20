# Edgar CLI Tab Completion Implementation

## Phase 1: Basic argcomplete Integration

### Setup & Dependencies

- [ ] Add `argcomplete` to project dependencies
- [ ] Import and integrate `argcomplete` in `main.py`
- [ ] Generate shell completion scripts for bash/zsh
- [ ] Document installation instructions for users

### Implementation

```python
# In main.py
import argcomplete

def main(args):
    parser = argparse.ArgumentParser(...)
    add_arguments(parser)
    argcomplete.autocomplete(parser)  # Add before parse_args()
    args = parser.parse_args()
```

### Benefits Achieved

- **Subcommand completion**: `ep sel<TAB>` → `ep select`
- **Option completion**: `ep select --ti<TAB>` → `ep select --ticker`
- **Choice completion**: `ep select patterns --type <TAB>` → `roles concepts all`
- **Shortcut completion**: `ep select -<TAB>` → shows all available shortcuts

## Phase 2: Database-Driven Completions

### High-Value Custom Completers

- [ ] **Ticker completion**: Query entities table for matching symbols
- [ ] **Group completion**: Query groups table for available group names
- [ ] **Access number completion**: Recent filing access numbers (limited scope)

### Implementation Strategy

```python
# In cli/completion.py
def ticker_completer(prefix, **kwargs):
    conn = sqlite3.connect(get_default_db())
    result = db.queries.entity_select(conn, None)
    if is_ok(result):
        tickers = [e["ticker"] for e in result[1]]
        return [t for t in tickers if t.startswith(prefix.lower())]
    return []

def group_completer(prefix, **kwargs):
    conn = sqlite3.connect(get_default_db())
    result = db.queries.group_select(conn)
    if is_ok(result):
        groups = [g["group_name"] for g in result[1]]
        return [g for g in groups if g.lower().startswith(prefix.lower())]
    return []

# Integration in argument parsers
parser.add_argument('-t', '--ticker').completer = ticker_completer
parser.add_argument('-g', '--group').completer = group_completer
```

### Context-Aware Enhancements

- [ ] **Company-specific groups**: Filter group completions by ticker when both are present
- [ ] **Form type completion**: Complete common SEC form types
- [ ] **Pattern name completion**: Complete concept pattern names for specific groups

## Installation & Distribution

### User Setup

```bash
# Generate completion script
ep --print-completion bash > ~/.edgar_completion
echo "source ~/.edgar_completion" >> ~/.bashrc

# Or for zsh
ep --print-completion zsh > ~/.edgar_completion
echo "source ~/.edgar_completion" >> ~/.zshrc
```

### Development Integration

- [ ] Add completion script generation to build process
- [ ] Include completion setup in installation documentation
- [ ] Test completion behavior across different shell environments

## Implementation Priority

**Immediate value** (Phase 1):

- Subcommand completion reduces need to remember `select vs probe vs new`
- Option completion handles `-t` vs `--ticker` uncertainty
- Choice completion for `--type roles concepts all`

**Workflow enhancement** (Phase 2):

- Ticker completion for active exploration
- Group completion for pattern management
- Context-aware filtering for focused workflows

## Technical Considerations

**Performance**: Database queries during completion should be fast (<100ms)
**Error handling**: Completion failures should degrade gracefully
**Database location**: Respect `--db` argument and defaults system
**Caching**: Consider caching frequently-accessed completions (tickers, groups)

## Testing Strategy

- [ ] Test completion with various shell configurations
- [ ] Verify performance with larger datasets
- [ ] Test completion behavior with invalid/missing databases
- [ ] Document completion behavior for users