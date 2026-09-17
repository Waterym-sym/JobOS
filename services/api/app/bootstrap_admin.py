"""One-time, server-console-only first administrator bootstrap.

Run after Alembic upgrade, against a backed-up database. The password is read
from the terminal and never accepted on the command line or written to logs.
"""

import argparse
from getpass import getpass
from uuid import uuid4

import psycopg

from services.api.app.account_security import hash_password, normalize_email
from services.api.app.config import get_settings

PRIVATE_TABLES = (
    "batch_run",
    "raw_job",
    "raw_company",
    "shortlist",
    "screening_entry",
    "ws_event_inbox",
)


def bootstrap(email: str, password: str) -> None:
    normalized = normalize_email(email)
    password_hash = hash_password(password)
    database_url = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    user_id = uuid4()
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM account_user")
            row = cursor.fetchone()
            if row is None or row[0] != 0:
                raise RuntimeError("first-admin bootstrap requires zero existing accounts")
            cursor.execute(
                """INSERT INTO account_user
                   (id, email, password_hash, role, is_admin, display_name)
                   VALUES (%s, %s, %s, 'seeker', true, %s)""",
                (user_id, normalized, password_hash, "管理员"),
            )
            cursor.execute("INSERT INTO account_profile (user_id) VALUES (%s)", (user_id,))
            for table in PRIVATE_TABLES:
                # Table names are a fixed code constant, never user input.
                cursor.execute(f"UPDATE {table} SET owner_user_id = %s WHERE owner_user_id IS NULL", (user_id,))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first JobOS administrator")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    first = getpass("New administrator password (12-128 chars): ")
    second = getpass("Confirm password: ")
    if first != second:
        raise SystemExit("passwords did not match")
    try:
        bootstrap(args.email, first)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print("First administrator created; legacy private rows assigned.")


if __name__ == "__main__":
    main()
