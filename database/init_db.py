#!/usr/bin/env python3
"""Initialize SQLite database for database

This initializer is designed to be safe to run repeatedly:
- Creates core tables if they don't exist.
- Enables foreign key enforcement.
- Seeds minimal starter data only if domain tables are empty.

Tables created:
- app_info: metadata key/value store
- users: example table (kept for backward compatibility with existing flow)
- notes: note records
- tags: tag records
- note_tags: many-to-many relationship between notes and tags

Indexes:
- notes.updated_at, notes.created_at for sorting
- tags.name unique index via constraint
- note_tags(note_id), note_tags(tag_id) for joins
"""

import os
import sqlite3
from typing import Dict, List, Tuple

DB_NAME = "myapp.db"
DB_USER = "kaviasqlite"  # Not used for SQLite, but kept for consistency
DB_PASSWORD = "kaviadefaultpassword"  # Not used for SQLite, but kept for consistency
DB_PORT = "5000"  # Not used for SQLite, but kept for consistency

print("Starting SQLite setup...")

# Check if database already exists
db_exists = os.path.exists(DB_NAME)
if db_exists:
    print(f"SQLite database already exists at {DB_NAME}")
    # Verify it's accessible
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.execute("SELECT 1")
        conn.close()
        print("Database is accessible and working.")
    except Exception as e:
        print(f"Warning: Database exists but may be corrupted: {e}")
else:
    print("Creating new SQLite database...")


def _enable_foreign_keys(cur: sqlite3.Cursor) -> None:
    """Enable foreign key enforcement for this connection."""
    cur.execute("PRAGMA foreign_keys = ON")


def _create_core_tables(cur: sqlite3.Cursor) -> None:
    """Create core tables that existed previously (backward compatible)."""
    # Create initial schema
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS app_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Create a sample users table as an example (kept for existing flows)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _create_notes_domain_tables(cur: sqlite3.Cursor) -> None:
    """Create notes/tags/note_tags tables and supporting indexes.

    Design notes / invariants:
    - notes.id and tags.id are stable INTEGER PK AUTOINCREMENT identifiers.
    - note_tags enforces uniqueness for a (note_id, tag_id) pair.
    - Foreign keys use ON DELETE CASCADE to keep relationship table clean.
    """
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            is_archived INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS note_tags (
            note_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (note_id, tag_id),
            FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
        """
    )

    # Indexes for common access patterns (list/sort/search/join).
    # Note: we intentionally don't add a content FTS table here to keep scope minimal;
    # it can be added later without breaking current schema.
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_is_archived ON notes(is_archived)")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_note_tags_note_id ON note_tags(note_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_note_tags_tag_id ON note_tags(tag_id)")


def _upsert_app_info(cur: sqlite3.Cursor, kv: Dict[str, str]) -> None:
    """Upsert app_info keys (preserves existing initialization behavior)."""
    for k, v in kv.items():
        cur.execute(
            "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
            (k, v),
        )


def _table_row_count(cur: sqlite3.Cursor, table: str) -> int:
    """Return row count for a table; raises sqlite3.Error if table doesn't exist."""
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return int(cur.fetchone()[0])


def _seed_notes_tags_if_empty(cur: sqlite3.Cursor) -> None:
    """Insert minimal seed data so the app has usable starting notes/tags.

    Contract:
    - Only seeds when both notes and tags are empty (fresh-ish install).
    - Uses INSERTs and then creates note_tags relationships.
    - Safe on re-runs: if there is any data present, it will not duplicate seeds.
    """
    try:
        notes_count = _table_row_count(cur, "notes")
        tags_count = _table_row_count(cur, "tags")
    except sqlite3.Error as e:
        # If tables are missing, it's a programming error in init flow.
        raise RuntimeError(f"Seed failed because expected tables are missing: {e}") from e

    if notes_count > 0 or tags_count > 0:
        print("Seed skipped: notes/tags already contain data.")
        return

    print("Seeding starter notes/tags...")

    seed_tags: List[Tuple[str, str]] = [
        ("welcome", "#3b82f6"),
        ("tips", "#06b6d4"),
        ("work", "#64748b"),
    ]
    for name, color in seed_tags:
        cur.execute("INSERT INTO tags (name, color) VALUES (?, ?)", (name, color))

    # Fetch tag IDs for relationships
    cur.execute("SELECT id, name FROM tags")
    tag_id_by_name = {name: tag_id for (tag_id, name) in cur.fetchall()}

    seed_notes: List[Tuple[str, str]] = [
        (
            "Welcome to Note Keeper",
            "This is your first note.\n\n"
            "You can create, edit, delete, search, and tag notes.\n"
            "Try adding a new note and assigning tags.",
        ),
        (
            "Quick tips",
            "- Use tags to organize notes\n"
            "- Use search to find notes by title/content\n"
            "- Keep notes short and focused",
        ),
        (
            "Work log",
            "Example of a work note:\n"
            "• Standup notes\n"
            "• TODOs\n"
            "• Decisions",
        ),
    ]
    note_ids: List[int] = []
    for title, content in seed_notes:
        cur.execute("INSERT INTO notes (title, content) VALUES (?, ?)", (title, content))
        note_ids.append(int(cur.lastrowid))

    # Create relationships (note_tags)
    rels: List[Tuple[int, int]] = [
        (note_ids[0], tag_id_by_name["welcome"]),
        (note_ids[1], tag_id_by_name["tips"]),
        (note_ids[2], tag_id_by_name["work"]),
    ]
    for note_id, tag_id in rels:
        cur.execute(
            "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)",
            (note_id, tag_id),
        )

    print(f"Seed complete: {len(note_ids)} notes, {len(seed_tags)} tags.")


# Create database with sample tables
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# Ensure foreign keys are enforced
_enable_foreign_keys(cursor)

# Create schema (existing + new)
_create_core_tables(cursor)
_create_notes_domain_tables(cursor)

# Insert initial metadata (preserve existing keys)
_upsert_app_info(
    cursor,
    {
        "project_name": "database",
        "version": "0.1.0",
        "author": "John Doe",
        "description": "",
    },
)

# Seed starter notes/tags if needed
_seed_notes_tags_if_empty(cursor)

conn.commit()

# Get database statistics
cursor.execute(
    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
)
table_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM app_info")
record_count = cursor.fetchone()[0]

# Also report notes/tags counts for quick verification
try:
    cursor.execute("SELECT COUNT(*) FROM notes")
    notes_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM tags")
    tags_count = cursor.fetchone()[0]
except sqlite3.Error:
    notes_count = "n/a"
    tags_count = "n/a"

conn.close()

# Save connection information to a file
current_dir = os.getcwd()
connection_string = f"sqlite:///{current_dir}/{DB_NAME}"

try:
    with open("db_connection.txt", "w") as f:
        f.write("# SQLite connection methods:\n")
        f.write(f"# Python: sqlite3.connect('{DB_NAME}')\n")
        f.write(f"# Connection string: {connection_string}\n")
        f.write(f"# File path: {current_dir}/{DB_NAME}\n")
    print("Connection information saved to db_connection.txt")
except Exception as e:
    print(f"Warning: Could not save connection info: {e}")

# Create environment variables file for Node.js viewer
db_path = os.path.abspath(DB_NAME)

# Ensure db_visualizer directory exists
if not os.path.exists("db_visualizer"):
    os.makedirs("db_visualizer", exist_ok=True)
    print("Created db_visualizer directory")

try:
    with open("db_visualizer/sqlite.env", "w") as f:
        f.write(f'export SQLITE_DB="{db_path}"\n')
    print("Environment variables saved to db_visualizer/sqlite.env")
except Exception as e:
    print(f"Warning: Could not save environment variables: {e}")

print("\nSQLite setup complete!")
print(f"Database: {DB_NAME}")
print(f"Location: {current_dir}/{DB_NAME}")
print("")

print("To use with Node.js viewer, run: source db_visualizer/sqlite.env")

print("\nTo connect to the database, use one of the following methods:")
print(f"1. Python: sqlite3.connect('{DB_NAME}')")
print(f"2. Connection string: {connection_string}")
print(f"3. Direct file access: {current_dir}/{DB_NAME}")
print("")

print("Database statistics:")
print(f"  Tables: {table_count}")
print(f"  App info records: {record_count}")
print(f"  Notes: {notes_count}")
print(f"  Tags: {tags_count}")

# If sqlite3 CLI is available, show how to use it
try:
    import subprocess

    result = subprocess.run(["which", "sqlite3"], capture_output=True, text=True)
    if result.returncode == 0:
        print("")
        print("SQLite CLI is available. You can also use:")
        print(f"  sqlite3 {DB_NAME}")
except Exception:
    pass

# Exit successfully
print("\nScript completed successfully.")
