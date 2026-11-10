from __future__ import annotations

import html
import json
import re
from typing import Any, Dict

SAFE_INLINE_IMAGE_MIME_TYPES = {
    "image/avif",
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/vnd.microsoft.icon",
    "image/webp",
    "image/x-icon",
}

_CID_SRC_RE = re.compile(
    r"""(?P<prefix>\bsrc\s*=\s*)(?P<quote>["']?)(?P<value>cid:(?:<[^"'<>]+>|[^"' >]+))(?P=quote)""", re.IGNORECASE
)
_CID_KEYS = ("cid", "content_id", "contentId", "content-id", "contentIdHeader")
_DATA_URL_KEYS = ("data_url", "dataUrl", "content_data_url", "contentDataUrl")
_URL_KEYS = ("url", "content_url", "contentUrl", "download_url", "downloadUrl", "src")
_BASE64_KEYS = ("content_base64", "contentBase64", "base64", "data", "content")
_RESOURCE_COLLECTION_KEYS = (
    "attachments",
    "inline_attachments",
    "inlineAttachments",
    "inline_images",
    "inlineImages",
    "resources",
    "images",
)


def serialize_temp_email_payload(message: Dict[str, Any]) -> str:
    """序列化临时邮箱原始 payload，避免图片资源元数据在入库时丢失。"""
    try:
        return json.dumps(message or {}, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return str(message or "")


def load_temp_email_payload(raw_content: Any) -> Dict[str, Any]:
    """从数据库字段恢复临时邮箱原始 payload。"""
    if isinstance(raw_content, dict):
        return raw_content
    if not isinstance(raw_content, str) or not raw_content.strip():
        return {}
    try:
        payload = json.loads(raw_content)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def build_inline_resource_map(payload: Any) -> Dict[str, str]:
    """
    从上游 payload 中提取内联图片资源。

    legacy 临时邮箱 bridge 文档当前只明确暴露 html/content 字段；这里兼容未文档化但可能出现的
    attachments / inline_images / cid_map 等结构，至少为后续扩展保留链路。
    """
    payload_dict = load_temp_email_payload(payload)
    inline_resources: Dict[str, str] = {}

    cid_map = payload_dict.get("cid_map") or payload_dict.get("cidMap")
    if isinstance(cid_map, dict):
        for cid, resource in cid_map.items():
            _register_inline_resource(inline_resources, cid, _coerce_resource_src(resource))

    for key in _RESOURCE_COLLECTION_KEYS:
        items = payload_dict.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = _first_non_empty(item, _CID_KEYS)
            disposition = str(item.get("disposition") or "").strip().lower()
            is_inline = bool(
                item.get("is_inline") or item.get("isInline") or item.get("inline") or cid or disposition == "inline"
            )
            if not is_inline:
                continue
            _register_inline_resource(inline_resources, cid, _coerce_resource_src(item))

    return inline_resources


def score_temp_email_payload(payload: Any) -> int:
    """
    为临时邮箱 payload 估算“富内容”程度。

    目标不是绝对精确，而是避免 detail 富内容被列表接口的简化 payload 覆盖。
    """
    payload_dict = load_temp_email_payload(payload)
    if not payload_dict:
        return 0

    score = 0
    if str(payload_dict.get("html_content") or payload_dict.get("body_html") or "").strip():
        score += 20
    if build_inline_resource_map(payload_dict):
        score += 100
    if any(isinstance(payload_dict.get(key), list) and payload_dict.get(key) for key in _RESOURCE_COLLECTION_KEYS):
        score += 30
    if isinstance(payload_dict.get("cid_map") or payload_dict.get("cidMap"), dict) and (
        payload_dict.get("cid_map") or payload_dict.get("cidMap")
    ):
        score += 30

    score += min(len(payload_dict), 20)
    return score


def choose_richer_temp_email_payload(existing_payload: Any, incoming_payload: Any) -> str:
    """在已有 payload 和新 payload 之间保留信息更完整的一份。"""
    existing_score = score_temp_email_payload(existing_payload)
    incoming_score = score_temp_email_payload(incoming_payload)

    if incoming_score >= existing_score:
        return serialize_temp_email_payload(load_temp_email_payload(incoming_payload) or incoming_payload)
    return serialize_temp_email_payload(load_temp_email_payload(existing_payload) or existing_payload)


def rewrite_html_with_inline_resources(html_content: str, inline_resources: Dict[str, str]) -> str:
    """将 HTML 中可解析的 cid: 资源替换为可访问的 data/url。"""
    if not html_content or not inline_resources:
        return html_content or ""

    def _replace(match: re.Match[str]) -> str:
        resolved_src = resolve_inline_resource(inline_resources, match.group("value"))
        if not resolved_src:
            return match.group(0)
        quote = match.group("quote") or '"'
        return f"{match.group('prefix')}{quote}{html.escape(resolved_src, quote=True)}{quote}"

    return _CID_SRC_RE.sub(_replace, html_content)


def resolve_inline_resource(inline_resources: Dict[str, str], cid_reference: Any) -> str:
    """根据 cid 引用解析内联资源 URL。"""
    normalized = normalize_cid_reference(cid_reference)
    if not normalized:
        return ""
    return inline_resources.get(normalized, "")


def normalize_cid_reference(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower().startswith("cid:"):
        text = text[4:]
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1]
    return text.strip().lower()


def _register_inline_resource(inline_resources: Dict[str, str], cid: Any, src: str) -> None:
    normalized_cid = normalize_cid_reference(cid)
    if normalized_cid and src:
        inline_resources[normalized_cid] = src


def _coerce_resource_src(resource: Any) -> str:
    if isinstance(resource, str):
        return _normalize_resource_src(resource)

    if not isinstance(resource, dict):
        return ""

    direct_data_url = _first_non_empty(resource, _DATA_URL_KEYS)
    if direct_data_url:
        return _normalize_resource_src(direct_data_url)

    direct_url = _first_non_empty(resource, _URL_KEYS)
    if direct_url:
        return _normalize_resource_src(direct_url)

    base64_payload = _first_non_empty(resource, _BASE64_KEYS)
    if not base64_payload:
        return ""

    mime_type = _normalize_mime_type(resource.get("content_type") or resource.get("contentType") or resource.get("mime_type"))
    if not mime_type:
        mime_type = "application/octet-stream"

    return f"data:{mime_type};base64,{base64_payload}"


def _normalize_resource_src(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("data:"):
        return text
    if text.startswith(("http://", "https://", "blob:")):
        return text
    return text


def _normalize_mime_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text in SAFE_INLINE_IMAGE_MIME_TYPES:
        return text
    return text


def _first_non_empty(data: Dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""
