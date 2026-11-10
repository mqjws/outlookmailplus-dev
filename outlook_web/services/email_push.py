from __future__ import annotations

import os
import re
import smtplib
from email.message import EmailMessage
from typing import Any

from outlook_web.repositories import settings as settings_repo


class EmailPushError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        message_en: str,
        status: int = 502,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.message_en = message_en
        self.status = status
        self.details = details


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_recipient(recipient: str) -> str:
    normalized = str(recipient or "").strip()
    if not normalized:
        raise EmailPushError(
            "EMAIL_NOTIFICATION_RECIPIENT_NOT_CONFIGURED",
            "请先配置接收通知邮箱",
            message_en="Please configure the notification recipient email first",
            status=400,
        )
    if not EMAIL_RE.match(normalized):
        raise EmailPushError(
            "EMAIL_NOTIFICATION_RECIPIENT_INVALID",
            "接收通知邮箱格式无效",
            message_en="Invalid notification recipient email address",
            status=400,
        )
    return normalized


def _parse_int_env(name: str, default: int, *, code: str, message: str, message_en: str) -> int:
    raw_value = str(os.getenv(name, str(default))).strip() or str(default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise EmailPushError(
            code,
            message,
            message_en=message_en,
            status=503,
            details=f"{name}={raw_value}",
        ) from exc
    if value <= 0:
        raise EmailPushError(
            code,
            message,
            message_en=message_en,
            status=503,
            details=f"{name}={raw_value}",
        )
    return value


def get_email_push_service_config() -> dict[str, Any]:
    host = str(os.getenv("EMAIL_NOTIFICATION_SMTP_HOST", "")).strip()
    sender = str(os.getenv("EMAIL_NOTIFICATION_FROM", "")).strip()
    if not host or not sender:
        raise EmailPushError(
            "EMAIL_NOTIFICATION_SERVICE_UNAVAILABLE",
            "当前系统暂不可用邮件通知功能",
            message_en="Email notification is currently unavailable on this system",
            status=503,
        )

    port = _parse_int_env(
        "EMAIL_NOTIFICATION_SMTP_PORT",
        25,
        code="EMAIL_NOTIFICATION_SMTP_PORT_INVALID",
        message="邮件通知 SMTP 端口配置无效",
        message_en="Email notification SMTP port is invalid",
    )
    timeout = _parse_int_env(
        "EMAIL_NOTIFICATION_SMTP_TIMEOUT",
        15,
        code="EMAIL_NOTIFICATION_SMTP_TIMEOUT_INVALID",
        message="邮件通知 SMTP 超时配置无效",
        message_en="Email notification SMTP timeout is invalid",
    )
    use_tls = _env_bool("EMAIL_NOTIFICATION_SMTP_USE_TLS", default=port == 587)
    use_ssl = _env_bool("EMAIL_NOTIFICATION_SMTP_USE_SSL", default=port == 465)
    use_tls, use_ssl = _normalize_smtp_transport_mode(
        port=port,
        use_tls=use_tls,
        use_ssl=use_ssl,
    )

    return {
        "host": host,
        "sender": sender,
        "port": port,
        "username": str(os.getenv("EMAIL_NOTIFICATION_SMTP_USERNAME", "")).strip(),
        "password": str(os.getenv("EMAIL_NOTIFICATION_SMTP_PASSWORD", "")).strip(),
        "use_tls": use_tls,
        "use_ssl": use_ssl,
        "timeout": timeout,
    }


def is_email_push_configured() -> bool:
    try:
        get_email_push_service_config()
    except EmailPushError:
        return False
    return True


def is_email_notification_ready() -> bool:
    try:
        get_email_push_service_config()
        _validate_recipient(get_saved_notification_recipient())
    except EmailPushError:
        return False
    return True


def get_saved_notification_recipient() -> str:
    return settings_repo.get_setting("email_notification_recipient", "").strip()


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "")).strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _normalize_smtp_transport_mode(
    *,
    port: int,
    use_tls: bool,
    use_ssl: bool,
) -> tuple[bool, bool]:
    """按端口自动纠正 SMTP 传输模式，避免模式冲突导致测试/运行不稳定。"""
    if port == 587:
        return True, False
    if port == 465:
        return False, True
    if use_tls and use_ssl:
        # 非标准端口下若两者都开，优先保留 SSL 避免重复握手路径
        return False, True
    return use_tls, use_ssl


def _build_message(*, recipient: str, subject: str, text_body: str, html_body: str | None = None) -> EmailMessage:
    sender = get_email_push_service_config()["sender"]
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    return message


def send_email_message(*, recipient: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    recipient = _validate_recipient(recipient)
    config = get_email_push_service_config()
    message = _build_message(recipient=recipient, subject=subject, text_body=text_body, html_body=html_body)

    smtp_cls = smtplib.SMTP_SSL if config["use_ssl"] else smtplib.SMTP
    try:
        with smtp_cls(config["host"], config["port"], timeout=config["timeout"]) as client:
            if not config["use_ssl"]:
                client.ehlo()
                if config["use_tls"]:
                    client.starttls()
                    client.ehlo()
            if config["username"]:
                client.login(config["username"], config["password"])
            client.send_message(message)
    except EmailPushError:
        raise
    except Exception as exc:
        raise EmailPushError(
            "EMAIL_TEST_SEND_FAILED",
            "测试邮件发送失败",
            message_en="Failed to send test email",
            details=str(exc),
        ) from exc


def send_test_email() -> str:
    recipient = get_saved_notification_recipient()
    send_email_message(
        recipient=recipient,
        subject="[Outlook Email Plus] 测试邮件",
        text_body=(
            "这是一封 Outlook Email Plus 业务通知测试邮件。\n\n"
            "如果你收到这封邮件，说明当前项目中的邮件通知链路已经可以正常发送。"
        ),
        html_body=(
            "<p>这是一封 <strong>Outlook Email Plus</strong> 业务通知测试邮件。</p>"
            "<p>如果你收到这封邮件，说明当前项目中的邮件通知链路已经可以正常发送。</p>"
        ),
    )
    return recipient
