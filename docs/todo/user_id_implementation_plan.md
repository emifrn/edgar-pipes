# User-Assigned IDs Implementation Plan

## Problem Statement

Pattern IDs (`pattern_id`) are auto-incremented and database-specific, making
journal entries with `--id` non-repeatable across different databases. The
current workaround translates `--id` to `--names` at journal-write time, but
this creates hidden magic and verbose journal entries.

## Solution Overview

Introduce **user-assigned IDs** as optional convenience labels for patterns:
- Add `user_id` column to pattern tables (optional, user-assigned)
- Keep `pattern_id` as internal database primary key
- Patterns always identified by `(cik, name)` - stable and required
- User IDs scoped to `(cik, type)` - optional numeric shortcuts
- Journal stores exactly what user types (no translation)

## Architecture Changes

### Schema Changes

**Note:** Database will be regenerated from scratch. These are the complete table definitions.

```sql
-- concept_patterns table with user_id
CREATE TABLE concept_patterns (
    pattern_id INTEGER PRIMARY KEY,
    cik TEXT NOT NULL REFERENCES entities(cik) ON DELETE CASCADE,
    name TEXT NOT NULL,
    pattern TEXT NOT NULL,
    user_id INTEGER,
    UNIQUE(cik, name)
);
CREATE UNIQUE INDEX idx_concept_user_id ON concept_patterns(cik, user_id)
  WHERE user_id IS NOT NULL;

-- role_patterns table with user_id
CREATE TABLE role_patterns (
    pattern_id INTEGER PRIMARY KEY,
    cik TEXT NOT NULL REFERENCES entities(cik) ON DELETE CASCADE,
    pattern TEXT NOT NULL,
    user_id INTEGER,
    UNIQUE(cik, pattern)
);
CREATE UNIQUE INDEX idx_role_user_id ON role_patterns(cik, user_id)
  WHERE user_id IS NOT NULL;
```

### Groups Schema Change

This does not change.

```sql
CREATE TABLE groups (
    group_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
```

### Command Semantics

#### `new` Command - Creates Entities

**`new concept`** - Creates concept pattern
```bash
ep new concept -t TICKER -n NAME -p PATTERN [--uid USER_ID]
```
- Required: `-t`, `-n`, `-p`
- Optional: `--uid` (user-assigned convenience label)
- Creates pattern, optionally with user_id

**`new role`** - Creates role pattern
```bash
ep new role -t TICKER -p PATTERN [--uid USER_ID]
```
- Required: `-t`, `-p`
- Optional: `--uid`

**`new group`** - Creates empty group
```bash
ep new group NAME
```
- No ticker (groups are global)
- Creates empty container

#### `add` Command - Links Patterns to Groups

**`add concept`** - Links concepts to group
```bash
# Direct linking by user ID
ep add concept -g GROUP -t TICKER --id ID1 ID2 ID3

# Direct linking by names
ep add concept -g GROUP -t TICKER --names NAME1 NAME2

# Derivation with filtering (filters use AND logic)
ep add concept -g GROUP -t TICKER --from SOURCE_GROUP [--id ...] [--names ...] [--pattern ...] [--exclude ...]
```
- Required: `-g`, `-t`
- Selection modes:
  - Direct ID: `--id` without `--from`
  - Direct names: `--names` without `--from`
  - Derivation: `--from` with optional filters (`--id`, `--names`, `--pattern`, `--exclude`)
- Filter logic: When multiple filters specified, ALL must match (AND logic)
- Ticker resolves scoped identifiers
- Empty derivation (no matches): Warning, no error

**`add role`** - Links roles to group
```bash
ep add role -g GROUP -t TICKER --id ID1 ID2
ep add role -g GROUP -t TICKER --from SOURCE_GROUP [--id ...] [--pattern ...] [--exclude ...]
```
- Same logic as concept: filters use AND when combined with `--from`

## Files to Modify

### 1. db/store.py
- Add `user_id` column to `concept_patterns` table
- Add `user_id` column to `role_patterns` table
- Add UNIQUE constraints for `(cik, user_id)` per table

### 2. db/queries.py
**New functions needed:**
- `concept_pattern_get_by_user_id(conn, cik, user_id)` → get concept by user ID
- `role_pattern_get_by_user_id(conn, cik, user_id)` → get role by user ID
- `concept_pattern_insert_with_user_id(conn, cik, name, pattern, user_id)` → create with user ID
- `role_pattern_insert_with_user_id(conn, cik, pattern, user_id)` → create with user ID
- `concept_pattern_list_by_cik(conn, cik)` → list all concepts for CIK with user_id
- `role_pattern_list_by_cik(conn, cik)` → list all roles for CIK with user_id

**Functions to keep (still needed):**
- `concept_pattern_get_by_cik_name()` - required for `--names` linking mode
- `role_pattern_get_by_cik_pattern()` - may still be needed for lookups
- All other existing query functions remain

**Functions to update:**
- `concept_pattern_update()` - add user_id parameter support
- `role_pattern_update()` - add user_id parameter support

### 3. cli/new.py
**Complete restructure needed:**

**New argument structure:**
```python
# new concept
parser_new_concept.add_argument("-t", "--ticker", required=True)
parser_new_concept.add_argument("-n", "--name", required=True)
parser_new_concept.add_argument("-p", "--pattern", required=True)
parser_new_concept.add_argument("--uid", type=int, help="optional user-assigned ID")

# new role
parser_new_role.add_argument("-t", "--ticker", required=True)
parser_new_role.add_argument("-p", "--pattern", required=True)
parser_new_role.add_argument("--uid", type=int, help="optional user-assigned ID")

# new group
parser_new_group.add_argument("group_name")  # Just the name, no ticker
```

**Remove entirely:**
- `--from`, `--pattern`, `--exclude`, `--names` arguments (moving to `add`)
- `apply_pattern_filters()` function (moving to `add`)
- `derive_group()` function (moving to `add`)
- `link_patterns_to_group()` function (moving to `add`)
- ID-to-names translation logic
- Custom journal return `{"journal_cmd": ...}`

**New logic:**
- Simple pattern creation with optional user_id
- Validate user_id uniqueness within (cik, type) scope
- Normal return: `ok(None)` for all cases

### 4. cli/add.py
**Major expansion needed:**

**Move from new.py:**
- `apply_pattern_filters()` - adapt for AND logic with multiple filter types
- `derive_group()` - rename and adapt for linking (not creating)
- `link_patterns_to_group()` - keep as-is

**New argument structure:**
```python
# add concept
parser_add_concept.add_argument("-g", "--group", required=True)
parser_add_concept.add_argument("-t", "--ticker", required=True)

# Source selection (optional)
parser_add_concept.add_argument("--from", dest="source_group", help="derive from source group")

# Selection and filter arguments (work independently or with --from)
parser_add_concept.add_argument("--id", nargs="+", type=int, help="select/filter by user IDs")
parser_add_concept.add_argument("--names", nargs="+", help="select/filter by concept names")
parser_add_concept.add_argument("--pattern", help="filter by concept name regex")
parser_add_concept.add_argument("--exclude", help="exclude by concept name regex")

# Validation: at least one selection method required
# - Without --from: must specify --id or --names (direct linking)
# - With --from: can use --id, --names, --pattern, --exclude as filters (AND logic)
```

**Three operation modes:**
1. **Direct ID linking**: `--id 1 2 3` (no --from)
2. **Direct name linking**: `--names Cash Inventory` (no --from)
3. **Filtered derivation**: `--from Balance [filters...]` (filters optional, use AND logic)

**Filter logic with --from:**
- Multiple filters applied with AND logic
- Example: `--from Balance --id 1 2 --pattern "^Cash"` → patterns must have user_id in [1,2] AND name match "^Cash"
- Empty result: print warning, no error

**Logic changes:**
- Resolve `--id` via `concept_pattern_get_by_user_id()`
- Resolve `--names` via `concept_pattern_get_by_cik_name()`
- For `--from`: get patterns from source group, apply ALL filters (AND), link to target group

### 5. cli/modify.py
**Extend with user_id support:**

**New argument for concept:**
```python
parser_concept.add_argument("--uid", type=int, help="set/change user-assigned ID")
```

**New argument for role:**
```python
parser_role.add_argument("--uid", type=int, help="set/change user-assigned ID")
```

**Logic changes:**
- Validate user_id uniqueness within (cik, type) scope before update
- Update `_execute_modify_concepts()` to handle user_id changes
- Update `_execute_modify_roles()` to handle user_id changes
- Allow setting user_id on patterns that don't have one (NULL → value)
- Allow changing existing user_id
- Allow removing user_id (set to NULL) - syntax TBD

### 6. cli/select.py or cli/list.py
**Add user_id visibility for scoped listings:**

Users need to see which user_ids are available/taken within their scope (cik, type).

**Command examples:**
```bash
# List all concepts for a ticker with user_ids
ep select patterns -t AEO --type concept

# List all roles for a ticker with user_ids
ep select patterns -t AEO --type role
```

**Display format:**
- Add `user_id` column to pattern listings
- Show NULL/empty for patterns without user_ids
- Filter by ticker to show CIK-scoped view
- Sort by user_id to make gaps obvious
- Help users choose available IDs

### 7. main.py
**Code to remove:**
```python
# Remove this entire block (around line 85-90)
elif isinstance(result[1], dict) and "journal_cmd" in result[1]:
    # Command provided custom journal entry (e.g., new with --id translated to --names)
    if cli.journal.should_journal_command(current_cmd) and not cli.journal.is_silent():
        custom_cmd = result[1]["journal_cmd"]
        cli.journal.write_entry([custom_cmd], "OK", None)
```

All commands now return standard `ok(None)` or `ok(Cmd)`, no special journal handling.

## Implementation Steps

**Note:** Database will be regenerated from scratch. No migration scripts needed.

### Phase 1: Database Layer (db/)
1. Add user_id support to `db/store.py` schema
2. Implement new query functions in `db/queries.py`
3. Update existing query functions (concept_pattern_update, role_pattern_update)
4. Test all new queries in isolation

### Phase 2: Command Layer - new.py
1. Backup current `new.py`
2. Complete restructure:
   - New argument structure (separate subcommands)
   - Remove derivation logic
   - Simple pattern creation only
   - Remove custom journal returns
3. Test each subcommand independently

### Phase 3: Command Layer - add.py
1. Backup current `add.py`
2. Move derivation logic from `new.py`
3. Add new argument handling for --from with filters
4. Implement AND filter logic
5. Implement three linking modes
6. Test linking in isolation

### Phase 4: Command Extensions - modify.py and select.py
1. Add `--user-id` argument to `modify concept` and `modify role`
2. Update execute functions to handle user_id
3. Add user_id column to pattern listings in select/list commands
4. Test user_id modifications

### Phase 5: Cleanup
1. Remove custom journal handling from `main.py`
2. Verify no references to removed code
3. Update any documentation

### Phase 6: Integration Testing
1. Test complete workflows end-to-end
2. Test journal replay scenarios
3. Validate error handling

## Testing Strategy

### Unit Tests
```bash
# Pattern creation with user_id
ep new concept -t AEO -n "Cash" -p "^Cash.*" --uid 1
ep new concept -t AEO -n "Inventory" -p "^Inv.*" --uid 2

# Collision detection
ep new concept -t AEO -n "Other" -p "^Other.*" --uid 1  # Should FAIL

# Group creation
ep new group Balance

# Direct linking
ep add concept -g Balance -t AEO --id 1 2

# Derivation
ep new group "Current Assets"
ep add concept -g "Current Assets" -t AEO --from Balance --id 1 2
```

### Journal Replay Test
```bash
# Create patterns
ep new concept -t AEO -n "Cash" -p "^Cash.*" --uid 1
ep new concept -t AEO -n "Inventory" -p "^Inv.*" --uid 2

# Create group with patterns
ep new group Balance
ep add concept -g Balance -t AEO --id 1 2

# Check journal
ep history

# Replay in fresh database
rm store.db
ep journal replay
```

### Edge Cases
- User ID collision within (cik, type) - should error
- User ID works across different CIKs (same ID, different companies) - should work
- Mixing --id and --names in same command with --from (AND filter logic)
- Missing patterns when using --id (proper error with message)
- Empty --from derivation (no matches) - should warn, not error
- Using --id in journal before pattern is created - should error on replay
- AND filter logic: `--from Balance --id 1 2 --pattern "^Cash"` - must match ALL
- Modifying user_id to existing value (collision) - should error
- Listing patterns with user_ids in scope - should show gaps

## Migration Considerations

### For Existing Databases
- Patterns created before migration won't have user_ids (NULL)
- Users can optionally assign user_ids later via `modify` command
- Existing journals with --names continue to work
- No automatic user_id assignment (avoid conflicts)

### Backward Compatibility
- `--names` continues to work (preferred for patterns without user_ids)
- `--pattern` filtering continues to work
- Groups remain global (no schema change for groups)

## Rollback Plan

If issues arise:
1. Revert schema changes (drop user_id columns)
2. Restore backed up `new.py` and `add.py`
3. Restore custom journal handling in `main.py`
4. Previous solution continues to work

## Success Criteria

- ✓ User can create patterns with optional --id
- ✓ User IDs are unique within (cik, type) scope
- ✓ Linking by --id resolves correctly
- ✓ Journal entries are repeatable
- ✓ No hidden translation magic
- ✓ Both --id and --names work for linking
- ✓ Groups remain global (no ticker)
- ✓ All tests pass
- ✓ Journal replay works in fresh database

## Notes

- User IDs are optional - patterns without them use --names for linking
- User IDs are scoped - AEO's ID 1 ≠ AAPL's ID 1
- Groups are global - no ticker association
- Ticker always required for pattern operations (resolves scope)

## Key Clarifications from Discussion

1. **Filter Logic**: Multiple filters with `--from` use AND logic (all must match)
2. **Schema Approach**: No ALTER statements needed - database regenerated from scratch
3. **Query Functions**: Keep `concept_pattern_get_by_cik_name()` - still needed for `--names` mode
4. **Argument Structure**: `--from` works WITH filter arguments (not mutually exclusive)
5. **Empty Derivation**: Warn user, don't error
6. **Journal Ordering**: Using --id before definition should error on replay
7. **User ID Scope**: IDs scoped to (cik, type) - user only needs awareness within scope
8. **modify Command**: Extend existing `modify` command with `--user-id` support
9. **list/select Command**: Add user_id column visibility for scoped pattern listings
