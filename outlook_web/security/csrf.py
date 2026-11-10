from __future__ import annotations

import os
from typing import Callable, Optional, Tuple

try:
    from flask_wtf.csrf import CSRFProtect
    from flask_wtf.csrf import generate_csrf as _generate_csrf  # type: ignore

    CSRF_AVAILABLE = True
except ImportError:  # pragma: no cover
    CSRFProtect = None  # type: ignore
    _generate_csrf = None  # type: ignore
    CSRF_AVAILABLE = False
    print("Warning: flask-wtf not installed. Non-development startup requires this dependency.")


def generate_csrf():
    """生成 CSRF token（模块级别导出）"""
    if _generate_csrf is not None:
        return _generate_csrf()
    return None


def init_csrf(app) -> Tuple[Optional[object], Callable, Optional[Callable]]:
    """
    初始化 CSRF 保护；仅显式开发环境允许缺少依赖。
    返回：csrf 实例、csrf_exempt 装饰器、generate_csrf 函数（可能为 None）
    """
    if CSRF_AVAILABLE:
        csrf = CSRFProtect(app)  # type: ignore[misc]
        app.config["WTF_CSRF_TIME_LIMIT"] = None  # CSRF token 不过期
        app.config.setdefault("WTF_CSRF_SSL_STRICT", False)
        print("CSRF protection enabled")

        def csrf_exempt(f):
            return csrf.exempt(f)

        return csrf, csrf_exempt, _generate_csrf

    if os.getenv("FLASK_ENV", "production").strip().lower() != "development":
        raise RuntimeError("flask-wtf is required outside development; refusing to disable CSRF protection")

    app.config["WTF_CSRF_ENABLED"] = False
    app.config["WTF_CSRF_CHECK_DEFAULT"] = False
    print("CSRF protection disabled")

    def csrf_exempt(f):
        return f

    return None, csrf_exempt, None
