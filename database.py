"""Everything that talks to MySQL lives here.

The password comes from an environment variable instead of being typed in
this file, so it never ends up on GitHub. The defaults fit a normal local
MySQL install:

    DB_HOST      (default: localhost)
    DB_PORT      (default: 3306)
    DB_USER      (default: root)
    DB_PASSWORD  (default: empty)
    DB_NAME      (default: job_tracker)
"""

import os

import mysql.connector


def get_db():
    """Open a fresh connection to the job_tracker database."""
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "job_tracker"),
    )


def query_all(sql, params=()):
    """Run a SELECT and get every row back as a dictionary."""
    conn = get_db()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        conn.close()


def query_one(sql, params=()):
    """Same as query_all, but just the first row (or None if there isn't one)."""
    rows = query_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    """Run an INSERT, UPDATE or DELETE and save it.

    After an INSERT you get the new row's id back. Values always go in as
    %s parameters instead of being pasted into the SQL, which is what keeps
    SQL injection out.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()
