import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, jsonify, request, session

from outlook_web import config
from outlook_web.security import csrf
from outlook_web.security.auth import get_client_ip
from outlook_web.security.proxy import TrustedProxyFix, resolve_forwarded_client_ip


class DeploymentConfigTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_local_http_defaults_remain_compatible(self):
        settings = config.get_security_config()
        self.assertFalse(settings["SESSION_COOKIE_SECURE"])
        self.assertFalse(settings["WTF_CSRF_SSL_STRICT"])
        self.assertIsNone(settings["TRUSTED_HOSTS"])
        self.assertEqual(settings["MAX_CONTENT_LENGTH"], 10 * 1024 * 1024)

    def test_https_cookie_enables_strict_csrf(self):
        with patch.dict(os.environ, {"SESSION_COOKIE_SECURE": "true"}):
            settings = config.get_security_config()
        self.assertTrue(settings["SESSION_COOKIE_SECURE"])
        self.assertTrue(settings["WTF_CSRF_SSL_STRICT"])
        app = Flask(__name__)
        app.secret_key = "test-cookie-secret"
        app.config.update(settings)

        @app.get("/")
        def index():
            session["logged_in"] = True
            return "ok"

        response = app.test_client().get("/", base_url="https://outlook.example.test")
        self.assertIn("Secure", response.headers["Set-Cookie"])

    def test_invalid_security_configuration_fails_closed(self):
        for key, value in [
            ("MAX_CONTENT_LENGTH", "0"),
            ("MAX_BATCH_ACCOUNTS", "bad"),
            ("MAX_BATCH_FOLDERS", "-1"),
            ("SESSION_COOKIE_SECURE", "tru"),
        ]:
            with self.subTest(key=key), patch.dict(os.environ, {key: value}):
                with self.assertRaises(RuntimeError):
                    config.get_security_config()

    def test_trusted_hosts_reject_unexpected_host(self):
        with patch.dict(os.environ, {"TRUSTED_HOSTS": "outlook.example.test, localhost"}):
            settings = config.get_security_config()
        app = Flask(__name__)
        app.config.update(settings)
        app.add_url_rule("/healthz", view_func=lambda: "ok")
        client = app.test_client()
        self.assertEqual(client.get("/healthz", base_url="http://outlook.example.test").status_code, 200)
        self.assertEqual(client.get("/healthz", base_url="http://localhost").status_code, 200)
        self.assertEqual(client.get("/healthz", base_url="http://attacker.example.test").status_code, 400)

    def test_oversized_request_body_returns_413(self):
        app = Flask(__name__)
        app.config.update(config.get_security_config())
        app.config["MAX_CONTENT_LENGTH"] = 8
        app.add_url_rule("/upload", view_func=lambda: request.get_data(), methods=["POST"])
        self.assertEqual(app.test_client().post("/upload", data=b"0123456789").status_code, 413)

    def test_missing_csrf_dependency_aborts_production(self):
        with patch.object(csrf, "CSRF_AVAILABLE", False), patch.dict(os.environ, {"FLASK_ENV": "production"}):
            with self.assertRaises(RuntimeError):
                csrf.init_csrf(Flask(__name__))

    def test_missing_csrf_dependency_only_allows_explicit_development(self):
        app = Flask(__name__)
        with patch.object(csrf, "CSRF_AVAILABLE", False), patch.dict(os.environ, {"FLASK_ENV": "development"}):
            protection, _, _ = csrf.init_csrf(app)
        self.assertIsNone(protection)
        self.assertFalse(app.config["WTF_CSRF_ENABLED"])

    def test_csrf_initialization_preserves_https_strict_setting(self):
        app = Flask(__name__)
        app.config["WTF_CSRF_SSL_STRICT"] = True
        csrf.init_csrf(app)
        self.assertTrue(app.config["WTF_CSRF_SSL_STRICT"])


class TrustedProxyTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"TRUSTED_PROXIES": "127.0.0.1"})
        environment.start()
        self.addCleanup(environment.stop)
        self.app = Flask(__name__)
        self.app.wsgi_app = TrustedProxyFix(self.app.wsgi_app, ["127.0.0.1"])

        @self.app.get("/")
        def index():
            return jsonify(client_ip=get_client_ip(), scheme=request.scheme, host=request.host, prefix=request.script_root)

    def test_untrusted_peer_cannot_spoof_proxy_headers(self):
        response = self.app.test_client().get(
            "/",
            headers={"X-Forwarded-For": "10.0.0.1", "X-Forwarded-Proto": "https"},
            environ_overrides={"REMOTE_ADDR": "203.0.113.10"},
        )
        self.assertEqual(response.json["client_ip"], "203.0.113.10")
        self.assertEqual(response.json["scheme"], "http")

    def test_trusted_peer_uses_only_single_hop_ip_and_scheme(self):
        response = self.app.test_client().get(
            "/",
            headers={
                "X-Forwarded-For": "10.0.0.1, 203.0.113.10",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "attacker.example.test",
                "X-Forwarded-Prefix": "/attacker",
            },
        )
        self.assertEqual(response.json["client_ip"], "203.0.113.10")
        self.assertEqual(response.json["scheme"], "https")
        self.assertEqual(response.json["host"], "localhost")
        self.assertEqual(response.json["prefix"], "")

    def test_unwrapped_ip_resolution_ignores_spoofed_leftmost_ip(self):
        self.assertEqual(resolve_forwarded_client_ip("127.0.0.1", "10.0.0.1, 203.0.113.10", ["127.0.0.1"]), "203.0.113.10")
        self.assertEqual(resolve_forwarded_client_ip("127.0.0.1", "10.0.0.1, invalid", ["127.0.0.1"]), "127.0.0.1")

    def test_proxy_fix_requires_valid_explicit_peers(self):
        for peers in [[], ["not-an-ip"]]:
            with self.subTest(peers=peers), self.assertRaises(RuntimeError):
                TrustedProxyFix(self.app.wsgi_app, peers)


class DeploymentArtifactTests(unittest.TestCase):
    def test_dockerfile_only_copies_application_sources(self):
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("COPY . .", dockerfile)
        self.assertIn("COPY outlook_web/ ./outlook_web/", dockerfile)
        ignored = (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
        for pattern in [".env", ".env.*", "*.txt", "!requirements.txt", ".runtime/", "session/"]:
            self.assertIn(pattern, ignored)

    def test_html_sanitizer_is_local_and_matches_official_release(self):
        root = Path(__file__).resolve().parents[1]
        template = (root / "templates/index.html").read_text(encoding="utf-8")
        self.assertIn("vendor/dompurify/purify.min.js", template)
        self.assertNotIn("cdn.jsdelivr.net/npm/dompurify", template)
        scripts = (root / "templates/partials/scripts.html").read_text(encoding="utf-8")
        self.assertIn("APP_VERSION }}-html-security-1", scripts)
        content = (root / "static/vendor/dompurify/purify.min.js").read_bytes()
        self.assertEqual(
            hashlib.sha256(content).hexdigest(), "2ffc14b99b081b271d8df0740b688e0163bc5f0fdfc3e1888acc88f005ab0700"
        )
