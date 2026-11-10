from __future__ import annotations

from flask import Blueprint

from outlook_web.controllers import tags as tags_controller


def create_blueprint() -> Blueprint:
    """创建 tags Blueprint"""
    bp = Blueprint("tags", __name__)
    bp.add_url_rule("/api/tags", view_func=tags_controller.api_get_tags, methods=["GET"])
    bp.add_url_rule("/api/tags", view_func=tags_controller.api_add_tag, methods=["POST"])
    bp.add_url_rule(
        "/api/tags/<int:tag_id>",
        view_func=tags_controller.api_delete_tag,
        methods=["DELETE"],
    )
    return bp
