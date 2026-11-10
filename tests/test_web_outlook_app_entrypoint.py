from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class WebOutlookAppEntrypointTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory(prefix="outlook-main-entrypoint-")
        self._db_path = Path(self._temp_dir.name) / "test.db"
        self._original_env = {
            key: os.environ.get(key)
            for key in (
                "SECRET_KEY",
                "LOGIN_PASSWORD",
                "SCHEDULER_AUTOSTART",
                "FLASK_ENV",
                "HOST",
                "PORT",
                "DATABASE_PATH",
            )
        }
        if "outlook_web.app" in sys.modules:
            sys.modules["outlook_web.app"]._APP_INSTANCE = None
        sys.modules.pop("web_outlook_app", None)
        os.environ["SECRET_KEY"] = "test-secret-key-32bytes-minimum-0000000000000000"
        os.environ["LOGIN_PASSWORD"] = "testpass123"
        os.environ["SCHEDULER_AUTOSTART"] = "false"
        os.environ["FLASK_ENV"] = "production"
        os.environ["HOST"] = "127.0.0.1"
        os.environ["PORT"] = "5099"
        os.environ["DATABASE_PATH"] = str(self._db_path)
        self.module = importlib.import_module("web_outlook_app")

    def tearDown(self) -> None:
        if "outlook_web.app" in sys.modules:
            sys.modules["outlook_web.app"]._APP_INSTANCE = None
        sys.modules.pop("web_outlook_app", None)
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._temp_dir.cleanup()

    def test_main_respects_scheduler_autostart_false(self) -> None:
        with (
            patch.object(self.module.scheduler_service, "should_autostart_scheduler", return_value=False) as should_autostart,
            patch.object(self.module.scheduler_service, "init_scheduler") as init_scheduler,
            patch.object(self.module.app, "run") as run_app,
        ):
            self.module.main()

        should_autostart.assert_called_once_with()
        init_scheduler.assert_not_called()
        run_app.assert_called_once_with(debug=False, host="127.0.0.1", port=5099)


if __name__ == "__main__":
    unittest.main()
