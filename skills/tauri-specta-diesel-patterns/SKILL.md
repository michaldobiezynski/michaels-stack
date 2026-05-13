---
name: tauri-specta-diesel-patterns
description: |
  Tauri + specta TypeScript binding generation and Diesel SQLite migration
  patterns for pawn-au-chocolat. Use when: (1) adding new Tauri commands
  and TypeScript bindings aren't updating after cargo build,
  (2) adding columns to existing SQLite tables without Diesel migrations,
  (3) Diesel Queryable derive fails after schema changes.
  Covers specta export timing, idempotent ALTER TABLE, and column ordering.
author: Claude Code
version: 1.0.0
date: 2026-04-01
---

# Tauri + Specta + Diesel Patterns

## Problem 1: TypeScript Bindings Not Regenerating

### Context / Trigger Conditions
- Added new `#[tauri::command]` with `#[specta::specta]`
- Ran `cargo build` but `src/bindings/generated.ts` doesn't contain the new command
- New commands show as undefined in TypeScript

### Solution
In pawn-au-chocolat, specta export runs inside `main()` behind `#[cfg(debug_assertions)]`:

```rust
#[cfg(debug_assertions)]
specta_builder
    .export(
        Typescript::default().bigint(BigIntExportBehavior::BigInt),
        "../src/bindings/generated.ts",
    )
    .expect("Failed to export types");
```

This means **`cargo build` alone does NOT regenerate bindings**. The binary must
actually **execute** (i.e., the app must start in dev mode) for the export to run.

**Workaround**: Manually add the binding to `generated.ts` following the existing
pattern. The next app launch in dev mode will regenerate correctly since the Rust
types are already in place.

```typescript
async myNewCommand(arg1: string, arg2: number) : Promise<Result<ReturnType, string>> {
    try {
    return { status: "ok", data: await TAURI_INVOKE("my_new_command", { arg1, arg2 }) };
} catch (e) {
    if(e instanceof Error) throw e;
    else return { status: "error", error: e  as any };
}
},
```

### Verification
- Check that `src/bindings/generated.ts` contains the new command
- TypeScript compilation should pass with no errors on the command calls

---

## Problem 2: Adding Columns to SQLite Without Diesel Migrations

### Context / Trigger Conditions
- pawn-au-chocolat does NOT use Diesel's migration framework
- Schema is defined manually in `schema.rs` and created from `create.sql`
- Need to add a new column to an existing table for existing databases

### Solution: Idempotent ALTER TABLE via PRAGMA

```rust
#[derive(QueryableByName, Debug)]
struct ColumnInfo {
    #[diesel(sql_type = Text, column_name = "name")]
    name: String,
}

fn migrate_add_new_column(conn: &mut SqliteConnection) -> Result<(), diesel::result::Error> {
    let columns: Vec<ColumnInfo> =
        sql_query("PRAGMA table_info('TableName');").load::<ColumnInfo>(conn)?;
    let has_column = columns.iter().any(|c| c.name == "NewColumn");
    if !has_column {
        conn.batch_execute(
            "ALTER TABLE TableName ADD COLUMN NewColumn INTEGER NOT NULL DEFAULT 0;",
        )?;
    }
    Ok(())
}
```

**Where to call it**: In `get_db_or_create()` on first pool creation (not every
connection). Log errors instead of silently ignoring them — the migration may
legitimately fail for databases that don't have the target table (e.g., puzzle DBs):

```rust
if is_new_pool {
    if let Err(e) = migrate_add_new_column(&mut conn) {
        info!("Migration skipped for {}: {}", db_path, e);
    }
}
```

**Don't forget to update all three locations:**
1. `create.sql` — new column in CREATE TABLE
2. `schema.rs` — new field in `diesel::table!` macro
3. `models.rs` — new field in `Game` and `NewGame` structs

### Critical: Diesel Queryable Column Ordering
The `#[derive(Queryable)]` trait maps struct fields **by position**, not by name.
New columns MUST be added as the **last column** in:
- The SQL CREATE TABLE statement
- The `diesel::table!` macro in schema.rs
- The `Game` struct (and `NewGame` for insertions)

Mismatched ordering causes silent data corruption or runtime panics.

### Verification
- `cargo check` passes
- Opening an existing database doesn't error
- New column has correct default value for existing rows
- Query results correctly map the new field

## Notes
- The `is_new_pool` check in `get_db_or_create` prevents running the migration
  on every connection — only on first pool creation per database path
- For re-import persistence of flags, use a propagation query that matches via
  a stable identifier (e.g., SiteID for game URLs) after each import
- SQLite's ALTER TABLE only supports ADD COLUMN — no DROP or RENAME COLUMN
  without recreating the table
