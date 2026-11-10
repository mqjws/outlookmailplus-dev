"""
错误处理中间件

功能：
- 处理可预期的 HTTP 异常
- 处理未捕获的异常
- 返回统一错误结构
"""

from __future__ import annotations

from flask import g, jsonify, request
from werkzeug.exceptions import HTTPException

from outlook_web.errors import build_error_payload

try:
    from flask_wtf.csrf import CSRFError
except ImportError:  # pragma: no cover
    CSRFError = None  # type: ignore


def _is_csrf_http_error(error: HTTPException) -> bool:
    return bool(CSRFError is not None and isinstance(error, CSRFError))


def _safe_error_details(*, status_code: int, error: Exception, expose_client_message: bool = False) -> str:
    if expose_client_message and status_code < 500:
        return str(error)
    return ""


def handle_http_exception(error: HTTPException):
    """处理可预期的 HTTP 异常，返回统一错误结构（仅对 API/JSON 请求返回 JSON）"""
    status_code = error.code or 500

    message_map = {
        400: "请求参数错误",
        401: "未授权",
        403: "无权限",
        404: "资源不存在",
        405: "请求方法不被允许",
        429: "请求过于频繁，请稍后再试",
    }
    message = message_map.get(status_code, "请求失败")

    trace_id_value = None
    try:
        trace_id_value = getattr(g, "trace_id", None)
    except Exception:
        trace_id_value = None

    if _is_csrf_http_error(error):
        error_payload = build_error_payload(
            code="CSRF_TOKEN_INVALID",
            message="会话已失效，请刷新页面后重试",
            message_en="Your session security token expired. Refresh the page and try again.",
            err_type="CSRFError",
            status=status_code,
            details=_safe_error_details(status_code=status_code, error=error, expose_client_message=True),
            trace_id=trace_id_value,
        )
    else:
        error_payload = build_error_payload(
            code="HTTP_ERROR",
            message=message,
            err_type="HttpError",
            status=status_code,
            details=_safe_error_details(status_code=status_code, error=error),
            trace_id=trace_id_value,
        )

    if request.path.startswith("/api/") or request.is_json:
        return jsonify({"success": False, "error": error_payload}), status_code

    return f"{message} (trace_id={error_payload.get('trace_id')})", status_code


def handle_exception(error):
    """处理未捕获的异常"""
    trace_id_value = None
    try:
        trace_id_value = getattr(g, "trace_id", None)
    except Exception:
        trace_id_value = None

    try:
        from flask import current_app

        current_app.logger.exception("Unhandled exception trace_id=%s", trace_id_value or "unknown")
    except Exception:
        pass

    error_payload = build_error_payload(
        code="INTERNAL_ERROR",
        message="服务器内部错误",
        err_type="UnhandledException",
        status=500,
        details="",
        trace_id=trace_id_value,
    )

    if request.path.startswith("/api/") or request.is_json:
        return jsonify({"success": False, "error": error_payload}), 500

    return f"服务器内部错误 (trace_id={error_payload.get('trace_id')})", 500
