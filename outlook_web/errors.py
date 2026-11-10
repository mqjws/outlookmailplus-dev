from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, Optional

from flask import current_app, g, jsonify

_FALLBACK_LOGGER = logging.getLogger("outlook_web.errors")
if not _FALLBACK_LOGGER.handlers:
    _FALLBACK_LOGGER.addHandler(logging.NullHandler())
_FALLBACK_LOGGER.propagate = False


ERROR_MESSAGE_EN_MAP = {
    "ACCOUNT_NOT_FOUND": "Account not found",
    "ACCOUNT_AUTH_EXPIRED": "Account authorization has expired. Please re-authorize the account",
    "ACCOUNT_IMPORT_FAILED": "Account import failed",
    "AUTH_REQUIRED": "Authentication required",
    "CSRF_TOKEN_INVALID": "Your session security token expired. Refresh the page and try again.",
    "CRONITER_NOT_INSTALLED": "croniter is not installed",
    "CRON_EXPRESSION_INVALID": "Invalid cron expression",
    "CRON_EXPRESSION_REQUIRED": "Cron expression is required",
    "EMAIL_NOTIFICATION_RECIPIENT_INVALID": "Invalid notification recipient email address",
    "EMAIL_NOTIFICATION_RECIPIENT_NOT_CONFIGURED": "Recipient email is not configured",
    "EMAIL_NOTIFICATION_RECIPIENT_REQUIRED": "Recipient email is required when email notification is enabled",
    "EMAIL_NOTIFICATION_SERVICE_UNAVAILABLE": "Email notification service is unavailable",
    "EMAIL_NOTIFICATION_SMTP_PORT_INVALID": "Email notification SMTP port is invalid",
    "EMAIL_NOTIFICATION_SMTP_TIMEOUT_INVALID": "Email notification SMTP timeout is invalid",
    "EMAIL_TEST_SEND_FAILED": "Failed to send test email",
    "EXPORT_VERIFY_REQUIRED": "Additional verification is required",
    "EXPORT_VERIFY_EXPIRED": "Verification expired. Please verify again",
    "EXPORT_VERIFY_IP_MISMATCH": "Verification failed because the client IP changed",
    "EXPORT_VERIFY_CLIENT_MISMATCH": "Verification failed because the client changed",
    "EXPORT_VERIFY_FAILED": "Verification failed. Please try again",
    "GROUP_DELETE_FAILED": "Failed to delete group",
    "GROUP_NAME_DUPLICATED": "Group name already exists",
    "GROUP_NAME_REQUIRED": "Group name is required",
    "GROUP_NOT_FOUND": "Group not found",
    "GROUP_VERIFICATION_LENGTH_INVALID": "Group verification code length is invalid",
    "GROUP_VERIFICATION_REGEX_INVALID": "Group verification regex is invalid",
    "GROUP_AI_MODEL_REQUIRED": "Group AI model ID is required",
    "VERIFICATION_AI_CONFIG_INCOMPLETE": "Verification AI configuration is incomplete",
    "GROUP_UPDATE_FAILED": "Failed to update group",
    "HTTP_ERROR": "Request failed",
    "INTERNAL_ERROR": "Internal server error",
    "LEGACY_ERROR": "Request failed",
    "WEBHOOK_URL_REQUIRED": "Webhook URL is required when webhook notification is enabled",
    "WEBHOOK_URL_INVALID": "Webhook URL must start with http:// or https://",
    "WEBHOOK_NOT_CONFIGURED": "Webhook notification is not configured",
    "WEBHOOK_TEST_SEND_FAILED": "Failed to send webhook test message",
    "WEBHOOK_SEND_FAILED": "Failed to send webhook message",
    "LOGIN_FAILED": "Login failed",
    "LOGIN_INVALID_PASSWORD": "Invalid password",
    "LOGIN_RATE_LIMITED": "Too many failed login attempts. Please try again later.",
    "OAUTH_CODE_INVALID": "Authorization code is invalid or expired",
    "OAUTH_CODE_PARSE_FAILED": "Failed to parse the authorization code from the callback",
    "OAUTH_CONFIG_INVALID": "OAuth configuration is invalid",
    "OAUTH_MICROSOFT_AUTH_FAILED": "Microsoft authorization failed",
    "OAUTH_MICROSOFT_REQUEST_FAILED": "Request to Microsoft OAuth failed",
    "OAUTH_REDIRECT_URI_MISMATCH": "The redirect URI does not match the configured OAuth redirect URI",
    "OAUTH_REFRESH_TOKEN_MISSING": "Microsoft did not return a refresh token",
    "OAUTH_VERIFY_TOKEN_REQUIRED": "Verification token is required",
    "DEFAULT_GROUP_PROTECTED": "The default group cannot be deleted",
    "SYSTEM_GROUP_PROTECTED": "System groups are protected",
    "TELEGRAM_NOT_CONFIGURED": "Telegram bot token and chat ID must be configured first",
    "TELEGRAM_TEST_SEND_FAILED": "Failed to send test message. Please check whether the Bot Token and Chat ID are correct",
}

STATUS_MESSAGE_EN_MAP = {
    400: "Bad request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    429: "Too many requests",
    500: "Internal server error",
}

ERROR_MESSAGE_MAP = {
    "ACCOUNT_NOT_FOUND": "账号不存在",
    "ACCOUNT_AUTH_EXPIRED": "账号授权已失效，请前往「刷新 Token」页面重新授权",
    "CSRF_TOKEN_INVALID": "会话已失效，请刷新页面后重试",
    "EMAIL_NOTIFICATION_RECIPIENT_INVALID": "接收通知邮箱格式无效",
    "EMAIL_NOTIFICATION_RECIPIENT_NOT_CONFIGURED": "请先配置接收通知邮箱",
    "EMAIL_NOTIFICATION_RECIPIENT_REQUIRED": "请填写接收通知邮箱",
    "EMAIL_NOTIFICATION_SERVICE_UNAVAILABLE": "当前系统暂不可用邮件通知功能",
    "EMAIL_NOTIFICATION_SMTP_PORT_INVALID": "邮件通知 SMTP 端口配置无效",
    "EMAIL_NOTIFICATION_SMTP_TIMEOUT_INVALID": "邮件通知 SMTP 超时配置无效",
    "EMAIL_TEST_SEND_FAILED": "测试邮件发送失败",
    "EXPORT_VERIFY_REQUIRED": "需要二次验证",
    "EXPORT_VERIFY_EXPIRED": "验证已过期，请重新验证",
    "EXPORT_VERIFY_IP_MISMATCH": "验证失败：IP 不匹配",
    "EXPORT_VERIFY_CLIENT_MISMATCH": "验证失败：客户端不匹配",
    "EXPORT_VERIFY_FAILED": "验证失败，请重试",
    "GROUP_DELETE_FAILED": "删除失败",
    "GROUP_NAME_DUPLICATED": "分组名称已存在",
    "GROUP_NAME_REQUIRED": "分组名称不能为空",
    "GROUP_NOT_FOUND": "分组不存在",
    "GROUP_VERIFICATION_LENGTH_INVALID": "分组验证码长度范围格式无效",
    "GROUP_VERIFICATION_REGEX_INVALID": "分组验证码正则表达式无效",
    "GROUP_AI_MODEL_REQUIRED": "请填写模型 ID",
    "VERIFICATION_AI_CONFIG_INCOMPLETE": "验证码 AI 配置不完整",
    "INVALID_PARAM": "参数错误",
    "WEBHOOK_URL_REQUIRED": "启用 Webhook 通知时必须填写 Webhook URL",
    "WEBHOOK_URL_INVALID": "Webhook URL 必须以 http:// 或 https:// 开头",
    "WEBHOOK_NOT_CONFIGURED": "请先完成 Webhook 配置并保存",
    "WEBHOOK_TEST_SEND_FAILED": "Webhook 测试发送失败",
    "WEBHOOK_SEND_FAILED": "Webhook 发送失败",
    "LOGIN_INVALID_PASSWORD": "密码错误",
    "LOGIN_RATE_LIMITED": "登录失败次数过多，请稍后再试",
    "OAUTH_CODE_INVALID": "授权码无效或已过期",
    "OAUTH_CODE_PARSE_FAILED": "无法从回跳结果中解析授权码",
    "OAUTH_CONFIG_INVALID": "OAuth 配置无效",
    "OAUTH_MICROSOFT_AUTH_FAILED": "微软授权失败",
    "OAUTH_MICROSOFT_REQUEST_FAILED": "请求微软 OAuth 服务失败",
    "OAUTH_REDIRECT_URI_MISMATCH": "redirect_uri 与当前 OAuth 配置不匹配",
    "OAUTH_REFRESH_TOKEN_MISSING": "微软未返回 refresh_token",
    "OAUTH_VERIFY_TOKEN_REQUIRED": "缺少 verify_token，请先完成二次验证",
    "TAG_NAME_DUPLICATED": "标签名称已存在",
    "TAG_NAME_REQUIRED": "标签名称不能为空",
    "TELEGRAM_NOT_CONFIGURED": "请先配置 Telegram Bot Token 和 Chat ID",
    "TELEGRAM_TEST_SEND_FAILED": "发送失败，请检查 Bot Token 和 Chat ID 是否正确",
    "DEFAULT_GROUP_PROTECTED": "默认分组不能删除",
    "SYSTEM_GROUP_PROTECTED": "系统分组受保护",
}


def build_export_verify_failure_response(error_message: str):
    normalized = str(error_message or "").strip()
    mapping = {
        "需要二次验证": (
            "EXPORT_VERIFY_REQUIRED",
            "需要二次验证",
            "Additional verification is required",
        ),
        "验证已过期，请重新验证": (
            "EXPORT_VERIFY_EXPIRED",
            "验证已过期，请重新验证",
            "Verification expired. Please verify again",
        ),
        "验证失败：IP 不匹配": (
            "EXPORT_VERIFY_IP_MISMATCH",
            "验证失败：IP 不匹配",
            "Verification failed because the client IP changed",
        ),
        "验证失败：客户端不匹配": (
            "EXPORT_VERIFY_CLIENT_MISMATCH",
            "验证失败：客户端不匹配",
            "Verification failed because the client changed",
        ),
    }
    code, message, message_en = mapping.get(
        normalized,
        (
            "EXPORT_VERIFY_FAILED",
            normalized or "验证失败，请重试",
            "Verification failed. Please try again",
        ),
    )
    return build_error_response(
        code,
        message,
        message_en=message_en,
        status=401,
        extra={"need_verify": True},
    )


def generate_trace_id() -> str:
    return uuid.uuid4().hex


def sanitize_error_details(details: Optional[str]) -> str:
    if not details:
        return ""
    sanitized = details
    patterns = [
        (r"(?i)(bearer\s+)[A-Za-z0-9\-._~\+/]+=*", r"\1***"),
        (
            r"(?i)(refresh_token|access_token|token|password|passwd|secret)\s*[:=]\s*\"?[A-Za-z0-9\-._~\+/]+=*\"?",
            r"\1=***",
        ),
        (r"(?i)(\"refresh_token\"\s*:\s*\")[^\"]+(\"?)", r"\1***\2"),
        (r"(?i)(\"access_token\"\s*:\s*\")[^\"]+(\"?)", r"\1***\2"),
        (r"(?i)(\"password\"\s*:\s*\")[^\"]+(\"?)", r"\1***\2"),
        (r"(?i)(client_secret|refresh_token|access_token)=[^&\s]+", r"\1=***"),
    ]
    for pattern, repl in patterns:
        sanitized = re.sub(pattern, repl, sanitized)
    return sanitized


def resolve_message_en(code: Optional[str], status: int = 500) -> str:
    if code:
        mapped = ERROR_MESSAGE_EN_MAP.get(str(code).strip())
        if mapped:
            return mapped
    return STATUS_MESSAGE_EN_MAP.get(status, "Request failed")


def resolve_message(code: Optional[str], default_message: str = "请求失败") -> str:
    if code:
        mapped = ERROR_MESSAGE_MAP.get(str(code).strip())
        if mapped:
            return mapped
    return default_message


def build_error_payload(
    code: str,
    message: str,
    err_type: str = "Error",
    status: int = 500,
    details: Any = None,
    trace_id: Optional[str] = None,
    message_en: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(message, str):
        message = str(message)
    sanitized_message = sanitize_error_details(message) if message else ""
    if message_en is None:
        message_en = resolve_message_en(code, status)
    if not isinstance(message_en, str):
        message_en = str(message_en)
    sanitized_message_en = sanitize_error_details(message_en) if message_en else ""

    if details is not None and not isinstance(details, str):
        try:
            details = json.dumps(details, ensure_ascii=False)
        except Exception:
            details = str(details)
    sanitized_details = sanitize_error_details(details) if details else ""

    request_trace_id = None
    try:
        request_trace_id = getattr(g, "trace_id", None)
    except Exception:
        request_trace_id = None

    trace_id_value = trace_id or request_trace_id or generate_trace_id()
    payload = {
        "code": code,
        "message": sanitized_message or "请求失败",
        "message_en": sanitized_message_en or resolve_message_en(code, status),
        "type": err_type,
        "status": status,
        "details": sanitized_details,
        "trace_id": trace_id_value,
    }

    # 根据状态码选择日志级别：
    # - 5xx: ERROR（服务端错误）
    # - 4xx: WARNING（客户端错误，如验证失败、权限不足等，属于正常业务流程）
    # - 其他: INFO
    log_level = logging.ERROR if status >= 500 else (logging.WARNING if status >= 400 else logging.INFO)

    try:
        current_app.logger.log(
            log_level,
            "trace_id=%s code=%s status=%s type=%s details=%s",
            trace_id_value,
            code,
            status,
            err_type,
            sanitized_details,
        )
    except Exception:
        try:
            _FALLBACK_LOGGER.log(
                log_level,
                "trace_id=%s code=%s status=%s type=%s details=%s",
                trace_id_value,
                code,
                status,
                err_type,
                sanitized_details,
            )
        except Exception:
            pass

    return payload


def build_error_response(
    code: str,
    message: str | None = None,
    *,
    message_en: str | None = None,
    err_type: str = "Error",
    status: int = 400,
    details: Any = None,
    trace_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    payload = build_error_payload(
        code=code,
        message=message or resolve_message(code),
        err_type=err_type,
        status=status,
        details=details,
        trace_id=trace_id,
        message_en=message_en,
    )
    body: Dict[str, Any] = {
        "success": False,
        "error": payload,
        "trace_id": payload["trace_id"],
        "code": payload["code"],
        "message": payload["message"],
        "message_en": payload["message_en"],
        "status": payload["status"],
    }
    if extra:
        body.update(extra)
    return jsonify(body), status
