import sys
import sqlite3
from typing import Any

# Local modules
from edgar.result import Result, ok, err, is_ok, is_not_ok


def init(conn: sqlite3.Connection) -> Result[None,str]:
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.executescript("""

            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS entities (
                cik             TEXT PRIMARY KEY,
                ticker          TEXT NOT NULL,
                name            TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS concepts (
                cid             INTEGER PRIMARY KEY,
                cik             TEXT NOT NULL,
                taxonomy        TEXT NOT NULL,
                tag             TEXT NOT NULL,
                name            TEXT NOT NULL,
                FOREIGN KEY (cik) REFERENCES entities(cik) ON DELETE CASCADE,
                UNIQUE (cik, taxonomy, tag)
            );

            CREATE TABLE IF NOT EXISTS filings (
                access_no       TEXT PRIMARY KEY,
                cik             TEXT NOT NULL,
                form_type       TEXT NOT NULL,
                primary_doc     TEXT NOT NULL,
                filing_date     TEXT NOT NULL,
                xbrl_url        TEXT,
                is_xbrl         INTEGER NOT NULL CHECK (is_xbrl IN (0, 1)),
                is_ixbrl        INTEGER NOT NULL CHECK (is_ixbrl IN (0, 1)),
                is_amendment    INTEGER NOT NULL CHECK (is_amendment IN (0, 1)) DEFAULT 0,
                FOREIGN KEY (cik) REFERENCES entities(cik) ON DELETE CASCADE
            );

            -- Document Entity Information
            CREATE TABLE IF NOT EXISTS dei (
                did                     INTEGER PRIMARY KEY,
                access_no               TEXT NOT NULL UNIQUE,
                doc_type                TEXT,
                doc_period_end          TEXT,
                fiscal_year             TEXT,
                fiscal_month_day_start  TEXT,
                fiscal_month_day_end    TEXT,
                fiscal_period           TEXT,
                FOREIGN KEY (access_no) REFERENCES filings(access_no) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS roles (
                rid         INTEGER PRIMARY KEY,
                access_no   TEXT NOT NULL,
                name        TEXT NOT NULL,
                UNIQUE (access_no, name),
                FOREIGN KEY (access_no) REFERENCES filings(access_no) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS role_concepts (
                rid         INTEGER NOT NULL,
                cid         INTEGER NOT NULL,
                PRIMARY KEY (rid, cid),
                FOREIGN KEY (rid) REFERENCES roles(rid) ON DELETE CASCADE,
                FOREIGN KEY (cid) REFERENCES concepts(cid) ON DELETE CASCADE
            );

            -- Financial contexts (periods)
            CREATE TABLE IF NOT EXISTS contexts (
                xid             INTEGER PRIMARY KEY,
                start_date      TEXT NOT NULL,
                end_date        TEXT NOT NULL,
                mode            TEXT NOT NULL,
                CHECK (start_date IS NOT NULL AND end_date IS NOT NULL),
                CHECK (mode IN ('instant', 'quarter', 'semester', 'threeQ', 'year')),
                UNIQUE (start_date, end_date, mode)
            );

            -- Units for financial facts
            CREATE TABLE IF NOT EXISTS units (
                unid            INTEGER PRIMARY KEY,
                name            TEXT NOT NULL UNIQUE
            );

            -- Financial facts extracted from filings
            CREATE TABLE IF NOT EXISTS facts (
                fid             INTEGER PRIMARY KEY,
                rid             INTEGER NOT NULL,
                cid             INTEGER NOT NULL,
                xid             INTEGER NOT NULL,
                unid            INTEGER NOT NULL,
                value           NUMERIC NOT NULL,
                FOREIGN KEY (rid) REFERENCES roles(rid) ON DELETE CASCADE,
                FOREIGN KEY (cid) REFERENCES concepts(cid) ON DELETE CASCADE,
                FOREIGN KEY (xid) REFERENCES contexts(xid) ON DELETE CASCADE,
                FOREIGN KEY (unid) REFERENCES units(unid) ON DELETE CASCADE,
                UNIQUE (rid, cid, xid, unid)
            );

            -- Dimensional breakdowns for facts
            CREATE TABLE IF NOT EXISTS dimensions (
                fid             INTEGER NOT NULL,
                dimension       TEXT NOT NULL,
                member          TEXT NOT NULL,
                FOREIGN KEY (fid) REFERENCES facts(fid) ON DELETE CASCADE,
                PRIMARY KEY (fid, dimension)
            );

            CREATE TABLE IF NOT EXISTS groups (
                gid             INTEGER PRIMARY KEY,
                name            TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS role_patterns (
                pid             INTEGER PRIMARY KEY,
                cik             TEXT NOT NULL,
                name            TEXT NOT NULL,
                pattern         TEXT NOT NULL,
                note            TEXT,
                FOREIGN KEY (cik) REFERENCES entities(cik) ON DELETE CASCADE,
                UNIQUE (cik, name)
            );

            CREATE TABLE IF NOT EXISTS group_role_patterns (
                gid             INTEGER NOT NULL,
                pid             INTEGER NOT NULL,
                PRIMARY KEY (gid, pid),
                FOREIGN KEY (gid) REFERENCES groups(gid) ON DELETE CASCADE,
                FOREIGN KEY (pid) REFERENCES role_patterns(pid) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS concept_patterns (
                pid             INTEGER PRIMARY KEY,
                cik             TEXT NOT NULL,
                name            TEXT NOT NULL,
                pattern         TEXT NOT NULL,
                uid             INTEGER,
                note            TEXT,
                FOREIGN KEY (cik) REFERENCES entities(cik) ON DELETE CASCADE,
                UNIQUE (cik, name)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_concept_uid
                ON concept_patterns(cik, uid)
                WHERE uid IS NOT NULL;

            CREATE TABLE IF NOT EXISTS group_concept_patterns (
                gid             INTEGER NOT NULL,
                pid             INTEGER NOT NULL,
                PRIMARY KEY (gid, pid),
                FOREIGN KEY (gid) REFERENCES groups(gid) ON DELETE CASCADE,
                FOREIGN KEY (pid) REFERENCES concept_patterns(pid) ON DELETE CASCADE
            );
        """)
        cursor.close()
        conn.commit()
        return ok(None)
    except sqlite3.Error as e:
        if cursor:
            cursor.close()
        return err(f"db.init() sqlite3 error: {e}")


def select(conn: sqlite3.Connection, query: str, params: tuple = ()) -> Result[list[dict[str, Any]], str]:
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        keys = [desc[0] for desc in cursor.description]
        data = [dict(zip(keys, values)) for values in cursor.fetchall()]
        cursor.close()
        return ok(data)
    except sqlite3.Error as e:
        if cursor:
            cursor.close()
        return err(f"db.select(...) sqlite3 error: {e}")


def insert(conn: sqlite3.Connection, table: str, data: list[dict[str, Any]]) -> Result[int, str]:
    if not data:
        return ok(0)

    cursor = None
    try:
        key_str = ", ".join(data[0].keys())
        val_str = ", ".join(f":{k}" for k in data[0].keys())
        query = f"INSERT INTO {table} ({key_str}) VALUES ({val_str});"

        cursor = conn.cursor()
        cursor.executemany(query, data)
        count = cursor.rowcount
        cursor.close()
        conn.commit()
        return ok(count)
    except sqlite3.Error as e:
        if cursor:
            cursor.close()
        return err(f"db.insert({table}, ...) sqlite3 error: {e}")


def insert_or_ignore(conn: sqlite3.Connection, table: str, data: list[dict[str, Any]]) -> Result[int, str]:
    if not data:
        return ok(0)

    cursor = None
    try:
        key_str = ", ".join(data[0].keys())
        val_str = ", ".join(f":{k}" for k in data[0].keys())
        query = f"INSERT OR IGNORE INTO {table} ({key_str}) VALUES ({val_str});"

        cursor = conn.cursor()
        cursor.executemany(query, data)
        count = cursor.rowcount
        cursor.close()
        conn.commit()
        return ok(count)
    except sqlite3.Error as e:
        if cursor:
            cursor.close()
        return err(f"db.insert_or_ignore({table}, ...) sqlite3 error: {e}")


def delete(conn: sqlite3.Connection, table: str, key: str, values: list[Any]) -> Result[int, str]:
    if not values:
        return ok(0)

    cursor = None
    try:
        params = tuple(set(values))
        places = ",".join("?" for _ in params)
        query = f"DELETE FROM {table} WHERE {key} IN ({places})"

        cursor = conn.cursor()
        cursor.execute(query, params)
        count = cursor.rowcount
        cursor.close()
        conn.commit()
        return ok(count)
    except sqlite3.Error as e:
        if cursor:
            cursor.close()
        return err(f"db.delete({table}, {key}, ...) sqlite3 error: {e}")
