"""Database operations for deployment, run inside the backend container (called by install/upgrade/rollback scripts); works with the bundled SQL Server and customer-owned instances.

    python -m scripts.dbops wait [--timeout 180]   wait until the database accepts connections
    python -m scripts.dbops ensure                  create the database if missing (needs dbcreator; skipped when the DBA created it)
    python -m scripts.dbops backup NAME             back up to BACKUP_DIR/NAME.bak and print the full path
    python -m scripts.dbops restore FILE            overwrite the current database from a backup (for rollback; drops all connections)
    python -m scripts.dbops revision                print the alembic revision in the database

BACKUP_DIR is a directory **on the database server**: /var/opt/mssql/backup for the bundled SQL Server container (mapped to backups/ in the install directory);
for a customer-owned instance the DBA chooses it, and the SQL Server service account needs write access.
"""

import argparse
import os
import sys
import time

import pyodbc
from sqlalchemy.engine import make_url

from app.core.config import settings

BACKUP_DIR = os.environ.get("BACKUP_DIR", "/var/opt/mssql/backup")


def _odbc(database: str) -> str:
    url = make_url(settings.database_url)
    query = dict(url.query)
    driver = query.pop("driver", "ODBC Driver 18 for SQL Server")
    host = url.host or "localhost"
    server = f"{host},{url.port}" if url.port else host
    parts = [f"DRIVER={{{driver}}}", f"SERVER={server}", f"DATABASE={database}",
             f"UID={url.username}", f"PWD={{{(url.password or '').replace('}', '}}')}}}"]
    parts += [f"{k}={v}" for k, v in query.items()]
    return ";".join(parts)


def _db_name() -> str:
    name = make_url(settings.database_url).database
    if not name or not name.replace("_", "").isalnum():
        raise SystemExit(f"Invalid database name: {name}")
    return name


def _connect(database: str = "master") -> pyodbc.Connection:
    # BACKUP / RESTORE / CREATE DATABASE cannot run inside a transaction
    return pyodbc.connect(_odbc(database), autocommit=True, timeout=10)


def _run(sql: str, *params) -> None:
    with _connect() as conn:
        cur = conn.execute(sql, *params)
        # Backup/restore progress messages come back as multiple result sets; read them all for the statement to complete
        while cur.nextset():
            pass


def wait(timeout: int) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            _connect().close()
            print("Database is ready")
            return
        except pyodbc.Error as exc:
            if time.time() > deadline:
                raise SystemExit(f"Timed out waiting for the database: {exc}") from exc
            time.sleep(3)


def ensure() -> None:
    name = _db_name()
    with _connect() as conn:
        exists = conn.execute("SELECT 1 FROM sys.databases WHERE name = ?", name).fetchone()
        if exists:
            print(f"Database {name} already exists")
            return
        # All text columns are Unicode; this case-insensitive collation also avoids codes that differ only in case
        conn.execute(f"CREATE DATABASE [{name}] COLLATE Chinese_PRC_CI_AS")
        print(f"Created database {name}")


def backup(label: str) -> None:
    if not label.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise SystemExit(f"Backup name may only contain letters, digits, - _ .: {label}")
    path = f"{BACKUP_DIR.rstrip('/')}/{label}.bak"
    # COPY_ONLY: does not break the customer DBA's own full/differential backup chain
    _run(f"BACKUP DATABASE [{_db_name()}] TO DISK = ? WITH COPY_ONLY, INIT, CHECKSUM", path)
    _run("RESTORE VERIFYONLY FROM DISK = ? WITH CHECKSUM", path)
    print(path)


def restore(path: str) -> None:
    name = _db_name()
    _run(f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
    try:
        _run(f"RESTORE DATABASE [{name}] FROM DISK = ? WITH REPLACE, CHECKSUM", path)
    finally:
        _run(f"ALTER DATABASE [{name}] SET MULTI_USER")
    print(f"Restored database {name} from {path}")


def revision() -> None:
    with _connect(_db_name()) as conn:
        try:
            print(conn.execute("SELECT version_num FROM alembic_version").fetchval())
        except pyodbc.ProgrammingError:
            print("none")


def main() -> None:
    parser = argparse.ArgumentParser(description="Database operations for deployment")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("wait").add_argument("--timeout", type=int, default=180)
    sub.add_parser("ensure")
    sub.add_parser("backup").add_argument("name")
    sub.add_parser("restore").add_argument("file")
    sub.add_parser("revision")
    args = parser.parse_args()
    try:
        if args.cmd == "wait":
            wait(args.timeout)
        elif args.cmd == "ensure":
            ensure()
        elif args.cmd == "backup":
            backup(args.name)
        elif args.cmd == "restore":
            restore(args.file)
        else:
            revision()
    except pyodbc.Error as exc:
        print(f"Database operation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
