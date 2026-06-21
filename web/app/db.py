"""
db.py – SQLite helpers for users and projects.
Schema is created on first startup; admin/admin is the bootstrap account.
"""

import os
import sqlite3
import hashlib
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", "/app/data/users.db")
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")


# ── Connection helper ────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Schema ───────────────────────────────────────────────────────────────────

def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                username     TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin     INTEGER DEFAULT 0,
                created_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS projects (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name          TEXT NOT NULL,
                status        TEXT DEFAULT 'new',
                error_message TEXT,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS project_files (
                project_id      INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                syllabus_path   TEXT,
                parameters_path TEXT,
                variables_path  TEXT,
                result_path     TEXT
            );
        """)

        # Bootstrap admin account
        if not conn.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?,?,1)",
                ("admin", _hash("admin")),
            )


# ── Password helpers ─────────────────────────────────────────────────────────

def _hash(password: str) -> str:
    """PBKDF2-HMAC-SHA256 with random salt – stored as 'salt_hex:key_hex'."""
    import os as _os
    salt = _os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + ":" + key.hex()


def _verify(password: str, stored: str) -> bool:
    salt_hex, key_hex = stored.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return key.hex() == key_hex


# ── Users ────────────────────────────────────────────────────────────────────

def authenticate(username: str, password: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row and _verify(password, row["password_hash"]):
        return dict(row)
    return None


def list_users() -> list[dict]:
    with _connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, username, is_admin, created_at FROM users ORDER BY created_at"
        ).fetchall()]


def create_user(username: str, password: str, is_admin: bool = False) -> bool:
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?,?,?)",
                (username, _hash(password), int(is_admin)),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def delete_user(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def change_password(user_id: int, new_password: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash(new_password), user_id),
        )


# ── Projects ─────────────────────────────────────────────────────────────────

def create_project(user_id: int, name: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO projects (user_id, name) VALUES (?,?)", (user_id, name)
        )
        pid = cur.lastrowid
        conn.execute("INSERT INTO project_files (project_id) VALUES (?)", (pid,))
    return pid


def get_project(project_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """SELECT p.*, pf.syllabus_path, pf.parameters_path,
                      pf.variables_path, pf.result_path
               FROM projects p
               LEFT JOIN project_files pf ON p.id = pf.project_id
               WHERE p.id = ?""",
            (project_id,),
        ).fetchone()
    return dict(row) if row else None


def get_user_projects(user_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT p.*, pf.syllabus_path, pf.parameters_path,
                      pf.variables_path, pf.result_path
               FROM projects p
               LEFT JOIN project_files pf ON p.id = pf.project_id
               WHERE p.user_id = ?
               ORDER BY p.created_at DESC""",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_project_status(project_id: int, status: str, error: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE projects SET status=?, error_message=? WHERE id=?",
            (status, error, project_id),
        )


def update_project_files(project_id: int, **fields) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [project_id]
    with _connect() as conn:
        conn.execute(
            f"UPDATE project_files SET {set_clause} WHERE project_id=?", values
        )


PROJECT_ROOT = os.environ.get("PROJECT_ROOT", "/app")


def input_dir(project_name: str) -> Path:
    """input/<project_name>/ — uploaded PDFs."""
    p = Path(PROJECT_ROOT) / "input" / project_name
    p.mkdir(parents=True, exist_ok=True)
    return p


def processing_dir(project_name: str) -> Path:
    """processing/<project_name>/ — parameters.env, variables.yml, parsed markdown."""
    p = Path(PROJECT_ROOT) / "processing" / project_name
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_dir(project_name: str) -> Path:
    """results/<project_name>/ — generated .docx files."""
    p = Path(PROJECT_ROOT) / "results" / project_name
    p.mkdir(parents=True, exist_ok=True)
    return p


# Keep backward compat alias
def project_dir(username: str, project_name: str) -> Path:
    """Deprecated — use input_dir / processing_dir / results_dir instead."""
    return processing_dir(project_name)
