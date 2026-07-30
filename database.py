import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "payroll.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            department TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'employee', 'manager')),
            base_salary REAL NOT NULL DEFAULT 0,
            team_size INTEGER DEFAULT 0,
            date_joined TEXT DEFAULT (date('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('present', 'absent')),
            UNIQUE(employee_id, date),
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
        )
    """)

    conn.commit()

    # Seed a default admin account if none exists
    existing_admin = cur.execute(
        "SELECT id FROM employees WHERE role = 'admin' LIMIT 1"
    ).fetchone()

    if not existing_admin:
        cur.execute(
            """INSERT INTO employees
               (name, email, password_hash, department, role, base_salary)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "Admin",
                "admin@company.com",
                generate_password_hash("admin123"),
                "Management",
                "admin",
                0,
            ),
        )
        conn.commit()

    conn.close()


def get_attendance_percent(employee_id):
    conn = get_db()
    total = conn.execute(
        "SELECT COUNT(*) c FROM attendance WHERE employee_id = ?", (employee_id,)
    ).fetchone()["c"]
    present = conn.execute(
        "SELECT COUNT(*) c FROM attendance WHERE employee_id = ? AND status = 'present'",
        (employee_id,),
    ).fetchone()["c"]
    conn.close()
    if total == 0:
        return 100.0  # no records yet -> assume full attendance
    return round((present / total) * 100, 2)
