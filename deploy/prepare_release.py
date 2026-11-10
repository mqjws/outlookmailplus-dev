import argparse
import os
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import tarfile
import tempfile
from contextlib import closing
from pathlib import Path

import bcrypt
from dotenv import dotenv_values

PUBLIC_FILES = (
    ".dockerignore",
    "compose.production.yaml",
    "requirements.txt",
    "web_outlook_app.py",
    "img/ico.png",
    "deploy/Dockerfile",
    "deploy/requirements.production.txt",
    "deploy/.env.production.example",
    "deploy/openresty-location.conf",
    "deploy/maintenance-location.conf",
    "deploy/1panel-outlook-vhost.conf",
    "deploy/backup.sh",
    "deploy/prepare_release.py",
    "deploy/refresh_cloudflare_ips.py",
    "docs/DEPLOYMENT_ARM64.md",
    "docs/SERVER_OPERATIONS.md",
    "docs/DEPLOYMENT_RECORD_20261104.md",
)
PUBLIC_DIRECTORIES = ("outlook_web", "templates", "static")
EXCLUDED_PARTS = {"__pycache__", "node_modules", ".git", ".runtime", "session"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".pem", ".key", ".txt", ".zip", ".tar", ".gz", ".log"}


def is_link(path):
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def iter_safe_files(directory):
    if is_link(directory):
        raise RuntimeError("Packaging refuses linked directories")
    root = directory.resolve()
    for candidate in sorted(directory.rglob("*")):
        relative = candidate.relative_to(directory)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if is_link(candidate) or not candidate.resolve().is_relative_to(root):
            raise RuntimeError("Packaging refuses symbolic links or paths outside the allowed directory")
        if candidate.is_file():
            yield candidate


def create_source_archive(project, destination):
    with tarfile.open(destination, "w:gz") as archive:
        for relative in PUBLIC_FILES:
            source = project / relative
            if is_link(source) or not source.resolve().is_relative_to(project.resolve()):
                raise RuntimeError("Invalid source file path")
            archive.add(source, arcname=relative, recursive=False)
        for relative in PUBLIC_DIRECTORIES:
            for source in iter_safe_files(project / relative):
                if source.name.startswith(".env") or source.suffix.lower() in EXCLUDED_SUFFIXES:
                    continue
                archive.add(source, arcname=source.relative_to(project).as_posix(), recursive=False)


def build_production_environment(settings):
    secret = settings.get("SECRET_KEY") or ""
    password = settings.get("LOGIN_PASSWORD") or ""
    if not secret.strip() or secret.strip() in {"your-secret-key-here", "REPLACE_WITH_ORIGINAL_LOCAL_SECRET_KEY"}:
        raise RuntimeError("A non-placeholder original SECRET_KEY is required; do not generate a different migration key")
    settings = dict(settings)
    if len(password) < 8 or password == "admin123":
        settings["LOGIN_PASSWORD"] = secrets.token_urlsafe(32)
    settings.update(
        PROXY_FIX_ENABLED="false",
        TRUSTED_PROXIES="",
        SCHEDULER_AUTOSTART="false",
        FLASK_ENV="production",
        DATABASE_PATH="/app/data/outlook_accounts.db",
        SESSION_COOKIE_SECURE="true",
        WTF_CSRF_SSL_STRICT="true",
        TRUSTED_HOSTS="outlook.ivano.cyou,localhost,127.0.0.1",
        DOCKER_SELF_UPDATE_ALLOW="false",
        GUNICORN_CMD_ARGS="",
    )
    lines = []
    for key, value in settings.items():
        if value is None:
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or any(character in value for character in "\r\n\x00"):
            raise RuntimeError("Environment keys must be valid identifiers and values must be single-line strings")
        lines.append(f"{key}={value}\n")
    return "".join(lines)


def backup_database(source, destination):
    if not source.is_file():
        raise RuntimeError("The configured local database does not exist")
    reader = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    writer = sqlite3.connect(destination)
    try:
        reader.backup(writer, pages=256, sleep=0.1)
        result = writer.execute("PRAGMA quick_check").fetchall()
        if result != [("ok",)]:
            raise RuntimeError("SQLite backup integrity check failed")
    finally:
        writer.close()
        reader.close()


def require_safe_stored_password(database, local_seed):
    if not database.is_file():
        raise RuntimeError("The configured local database does not exist")
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)) as reader:
        row = reader.execute("SELECT value FROM settings WHERE key='login_password'").fetchone()
    if not row or not row[0]:
        raise RuntimeError("The existing database must have a configured login password before migration")
    stored = row[0]
    weak_candidates = {"admin123", ""}
    if len(local_seed) < 8:
        weak_candidates.add(local_seed)
    for candidate in weak_candidates:
        matches = (
            bcrypt.checkpw(candidate.encode("utf-8"), stored.encode("utf-8"))
            if stored.startswith(("$2b$", "$2a$", "$2y$"))
            else stored == candidate
        )
        if matches:
            raise RuntimeError(
                "The existing database still uses a known weak login password. Change it in the local app's System Settings "
                "before packaging. Do not change SECRET_KEY; changing only LOGIN_PASSWORD in .env does not update the stored password."
            )
    if not stored.startswith(("$2b$", "$2a$", "$2y$")) and len(stored) < 8:
        raise RuntimeError("Change the short stored password in the local app's System Settings before packaging")


def create_private_archive(project, settings, destination):
    environment = build_production_environment(settings)
    database = Path(settings.get("DATABASE_PATH") or "data/outlook_accounts.db")
    if not database.is_absolute():
        database = project / database
    with tempfile.TemporaryDirectory(prefix="private-staging-", dir=destination.parent) as directory:
        staging = Path(directory)
        data = staging / "data"
        data.mkdir()
        backup_database(database, data / "outlook_accounts.db")
        require_safe_stored_password(data / "outlook_accounts.db", settings.get("LOGIN_PASSWORD") or "")
        (staging / ".env.production").write_text(environment, encoding="utf-8", newline="\n")
        plugins = database.resolve().parent / "plugins"
        if plugins.exists():
            for source in iter_safe_files(plugins):
                target = data / "plugins" / source.relative_to(plugins)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        with tarfile.open(destination, "w:gz") as archive:
            archive.add(data, arcname="data")
            archive.add(staging / ".env.production", arcname=".env.production")


def create_private_output(directory):
    directory.mkdir(mode=0o700)
    if os.name == "nt":
        account = subprocess.check_output(["whoami"], text=True).strip()
        subprocess.run(
            ["icacls", str(directory), "/inheritance:r", "/grant:r", f"{account}:(OI)(CI)F"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Prepare separate source and private migration archives; never upload anything"
    )
    parser.add_argument("--output", type=Path, required=True, help="A new directory outside the project")
    arguments = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    output = arguments.output.resolve()
    if output.is_relative_to(project) or output.exists():
        parser.error("Output must be a new directory outside the project")
    settings = dotenv_values(project / ".env")
    build_production_environment(settings)
    database = Path(settings.get("DATABASE_PATH") or "data/outlook_accounts.db")
    require_safe_stored_password(
        database if database.is_absolute() else project / database, settings.get("LOGIN_PASSWORD") or ""
    )
    create_private_output(output)
    try:
        create_source_archive(project, output / "outlook-source.tar.gz")
        create_private_archive(project, settings, output / "outlook-private.tar.gz")
    except Exception:
        for filename in ("outlook-source.tar.gz", "outlook-private.tar.gz"):
            (output / filename).unlink(missing_ok=True)
        raise
    print(f"Prepared: {output / 'outlook-source.tar.gz'}")
    print(f"Prepared: {output / 'outlook-private.tar.gz'} (contains credentials; keep private)")
    print("No files uploaded; original .env and database were not modified.")


if __name__ == "__main__":
    main()
