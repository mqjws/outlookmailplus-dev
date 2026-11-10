import io
import sqlite3
import tarfile
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from deploy import prepare_release, refresh_cloudflare_ips

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleasePackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.project = self.directory / "project"
        self.project.mkdir()
        for relative in prepare_release.PUBLIC_FILES:
            destination = self.project / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("public source", encoding="utf-8")
        for relative in prepare_release.PUBLIC_DIRECTORIES:
            directory = self.project / relative
            directory.mkdir(exist_ok=True)
            (directory / "public.py").write_text("public source", encoding="utf-8")
        self.settings = {"SECRET_KEY": "original-secret-with-$-and-'quotes'", "LOGIN_PASSWORD": "strong-password-123"}

    def test_source_archive_uses_allowlist_and_excludes_credentials(self):
        for relative in [
            ".env",
            "hotmail.com_7.txt",
            "data/outlook_accounts.db",
            "plugins/test.py",
            "img/private-screenshot.png",
            "static/.env.secret",
            "static/key.pem",
            "templates/accounts.txt",
        ]:
            destination = self.project / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("sensitive-marker", encoding="utf-8")
        archive_path = self.directory / "source.tar.gz"
        prepare_release.create_source_archive(self.project, archive_path)
        with tarfile.open(archive_path) as archive:
            names = archive.getnames()
            self.assertIn("deploy/requirements.production.txt", names)
            self.assertIn("static/public.py", names)
            self.assertIn("img/ico.png", names)
            self.assertNotIn(".env", names)
            for member in archive.getmembers():
                with archive.extractfile(member) as source:
                    self.assertNotIn(b"sensitive-marker", source.read())

    def test_source_archive_refuses_links_outside_allowlist(self):
        external = self.directory / "private.key"
        external.write_text("private", encoding="utf-8")
        try:
            (self.project / "static" / "linked.js").symlink_to(external)
        except OSError:
            self.skipTest("Symbolic links are unavailable")
        with self.assertRaises(RuntimeError):
            prepare_release.create_source_archive(self.project, self.directory / "source.tar.gz")

    def test_environment_preserves_original_secret_without_extra_quotes(self):
        environment = prepare_release.build_production_environment(self.settings)
        self.assertIn(f"SECRET_KEY={self.settings['SECRET_KEY']}\n", environment)
        self.assertIn("PROXY_FIX_ENABLED=false\n", environment)
        self.assertIn("SCHEDULER_AUTOSTART=false\n", environment)
        self.assertIn("SESSION_COOKIE_SECURE=true\n", environment)

    def test_environment_rejects_placeholder_migration_keys(self):
        for override in [{"SECRET_KEY": ""}, {"SECRET_KEY": "your-secret-key-here"}]:
            with self.subTest(override=override), self.assertRaises(RuntimeError):
                prepare_release.build_production_environment(self.settings | override)

    def test_weak_environment_seed_is_replaced_only_in_the_production_environment(self):
        settings = self.settings | {"LOGIN_PASSWORD": "short"}
        environment = prepare_release.build_production_environment(settings)
        password = next(line.split("=", 1)[1] for line in environment.splitlines() if line.startswith("LOGIN_PASSWORD="))
        self.assertGreaterEqual(len(password), 32)
        self.assertEqual(settings["LOGIN_PASSWORD"], "short")
        self.assertIn(f"SECRET_KEY={self.settings['SECRET_KEY']}\n", environment)

    def test_known_weak_stored_password_is_rejected_without_changing_database(self):
        database = self.directory / "weak.db"
        with closing(sqlite3.connect(database)) as writer:
            writer.execute("CREATE TABLE settings (key TEXT, value TEXT)")
            writer.execute("INSERT INTO settings VALUES ('login_password', 'short')")
            writer.commit()
        original = database.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "System Settings"):
            prepare_release.require_safe_stored_password(database, "short")
        self.assertEqual(database.read_bytes(), original)

    def test_hashed_weak_stored_password_is_rejected(self):
        database = self.directory / "weak-hashed.db"
        hashed = prepare_release.bcrypt.hashpw(b"short", prepare_release.bcrypt.gensalt(rounds=4)).decode("utf-8")
        with closing(sqlite3.connect(database)) as writer:
            writer.execute("CREATE TABLE settings (key TEXT, value TEXT)")
            writer.execute("INSERT INTO settings VALUES ('login_password', ?)", (hashed,))
            writer.commit()
        with self.assertRaisesRegex(RuntimeError, "System Settings"):
            prepare_release.require_safe_stored_password(database, "short")

    def test_strong_database_password_can_migrate_without_changing_the_weak_local_env_seed(self):
        database = self.directory / "strong-hashed.db"
        hashed = prepare_release.bcrypt.hashpw(b"strong-password-123", prepare_release.bcrypt.gensalt(rounds=4)).decode(
            "utf-8"
        )
        with closing(sqlite3.connect(database)) as writer:
            writer.execute("CREATE TABLE settings (key TEXT, value TEXT)")
            writer.execute("INSERT INTO settings VALUES ('login_password', ?)", (hashed,))
            writer.commit()
        prepare_release.require_safe_stored_password(database, "short")

    def test_environment_rejects_multiline_values_and_invalid_keys(self):
        for override in [{"OTHER": "first\nsecond"}, {"OTHER": "first\rsecond"}, {"BAD-KEY": "value"}, {"OTHER": "\x00"}]:
            with self.subTest(override=override), self.assertRaises(RuntimeError):
                prepare_release.build_production_environment(self.settings | override)

    def test_sqlite_backup_captures_wal_without_modifying_source_data(self):
        database = self.directory / "live.db"
        connection = sqlite3.connect(database)
        self.addCleanup(connection.close)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE accounts (email TEXT)")
        connection.execute("INSERT INTO accounts VALUES ('example@example.test')")
        connection.commit()
        snapshot = self.directory / "snapshot.db"
        prepare_release.backup_database(database, snapshot)
        with closing(sqlite3.connect(snapshot)) as reader:
            self.assertEqual(reader.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], 1)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], 1)

    def test_missing_database_does_not_create_an_empty_source(self):
        source = self.directory / "missing.db"
        with self.assertRaises(RuntimeError):
            prepare_release.backup_database(source, self.directory / "snapshot.db")
        self.assertFalse(source.exists())

    def test_private_archive_migrates_only_live_database_and_actual_data_plugins(self):
        data = self.project / "data"
        plugins = data / "plugins" / "temp_mail_providers"
        plugins.mkdir(parents=True)
        (plugins / "provider.py").write_text("installed provider", encoding="utf-8")
        (data / "old-backup.db").write_bytes(b"unrelated backup")
        database = data / "outlook_accounts.db"
        with closing(sqlite3.connect(database)) as writer:
            writer.execute("CREATE TABLE accounts (email TEXT)")
            writer.execute("INSERT INTO accounts VALUES ('example@example.test')")
            writer.execute("CREATE TABLE settings (key TEXT, value TEXT)")
            writer.execute("INSERT INTO settings VALUES ('login_password', 'strong-password-123')")
            writer.commit()
        original = database.read_bytes()
        destination = self.directory / "private.tar.gz"
        prepare_release.create_private_archive(self.project, self.settings, destination)
        with tarfile.open(destination) as archive:
            self.assertIn("data/plugins/temp_mail_providers/provider.py", archive.getnames())
            self.assertNotIn("data/old-backup.db", archive.getnames())
            with archive.extractfile(".env.production") as environment:
                self.assertIn(self.settings["SECRET_KEY"].encode(), environment.read())
        self.assertEqual(database.read_bytes(), original)


class ProductionManifestTests(unittest.TestCase):
    def setUp(self):
        self.compose = (PROJECT_ROOT / "compose.production.yaml").read_text(encoding="utf-8")

    def test_production_builds_hardened_source_for_arm64_without_watchtower(self):
        self.assertNotIn("watchtower", self.compose)
        self.assertIn("platform: linux/arm64", self.compose)
        self.assertIn("dockerfile: deploy/Dockerfile", self.compose)
        self.assertIn("pull_policy: never", self.compose)
        self.assertNotIn("latest", self.compose)

    def test_production_keeps_private_data_outside_image_and_port_off_public_interfaces(self):
        self.assertIn('"127.0.0.1:5001:5000"', self.compose)
        self.assertIn("format: raw", self.compose)
        self.assertIn("read_only: true", self.compose)
        self.assertIn('user: "1001:1001"', self.compose)
        self.assertIn('APP_UID: "1001"', self.compose)
        self.assertIn('APP_GID: "1001"', self.compose)
        self.assertIn("      - ALL", self.compose)
        self.assertEqual(self.compose.count("create_host_path: false"), 2)
        self.assertNotIn("docker.sock", self.compose)

    def test_public_https_and_host_validation_cannot_be_disabled_by_migrated_env(self):
        self.assertIn('SESSION_COOKIE_SECURE: "true"', self.compose)
        self.assertIn('WTF_CSRF_SSL_STRICT: "true"', self.compose)
        self.assertIn("TRUSTED_HOSTS: outlook.ivano.cyou,localhost,127.0.0.1", self.compose)
        self.assertIn("DATABASE_PATH: /app/data/outlook_accounts.db", self.compose)

    def test_production_dockerfile_uses_nonroot_single_worker_and_omits_request_query_logging(self):
        dockerfile = (PROJECT_ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("COPY . .", dockerfile)
        self.assertNotIn("COPY plugins/", dockerfile)
        self.assertIn("USER ${APP_UID}:${APP_GID}", dockerfile)
        self.assertIn("ARG APP_UID=1001", dockerfile)
        self.assertIn("ARG APP_GID=1001", dockerfile)
        for source in ("web_outlook_app.py", "outlook_web/", "templates/", "static/", "img/ico.png"):
            self.assertIn(f"COPY --chown=${{APP_UID}}:${{APP_GID}} {source}", dockerfile)
        self.assertIn('"--workers", "1", "--threads", "8"', dockerfile)
        self.assertNotIn("--preload", dockerfile)
        self.assertIn('"--no-control-socket"', dockerfile)
        self.assertIn("%(U)s", dockerfile)
        self.assertNotIn("%(q)s", dockerfile)
        self.assertNotIn("%(r)s", dockerfile)

    def test_reverse_proxy_overwrites_forwarded_headers_instead_of_appending_untrusted_input(self):
        configuration = (PROJECT_ROOT / "deploy" / "openresty-location.conf").read_text(encoding="utf-8")
        self.assertIn("X-Forwarded-For $remote_addr", configuration)
        self.assertIn("X-Forwarded-Proto $scheme", configuration)
        self.assertNotIn("$proxy_add_x_forwarded_for", configuration)
        self.assertNotIn("$http_cf_connecting_ip", configuration)


class CloudflareConfigurationTests(unittest.TestCase):
    def test_refresh_validates_lists_before_writing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            script_path = Path(directory) / "refresh_cloudflare_ips.py"
            with patch.object(refresh_cloudflare_ips, "__file__", str(script_path)), patch.object(
                refresh_cloudflare_ips.urllib.request,
                "urlopen",
                side_effect=[io.BytesIO(b"192.0.2.0/24\n"), io.BytesIO(b"2001:db8::/32\n")],
            ):
                refresh_cloudflare_ips.main()
            contents = (script_path.parent / "cloudflare-realip.conf").read_text(encoding="utf-8")
            self.assertIn("set_real_ip_from 192.0.2.0/24;", contents)
            self.assertIn("real_ip_header CF-Connecting-IP;", contents)

    def test_bad_address_list_does_not_replace_existing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            script_path = Path(directory) / "refresh_cloudflare_ips.py"
            destination = script_path.parent / "cloudflare-realip.conf"
            destination.write_text("original", encoding="utf-8")
            with patch.object(refresh_cloudflare_ips, "__file__", str(script_path)), patch.object(
                refresh_cloudflare_ips.urllib.request, "urlopen", return_value=io.BytesIO(b"<html>failure</html>")
            ):
                with self.assertRaises(ValueError):
                    refresh_cloudflare_ips.main()
            self.assertEqual(destination.read_text(encoding="utf-8"), "original")


if __name__ == "__main__":
    unittest.main()
