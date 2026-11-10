from __future__ import annotations

from flask import Blueprint

from outlook_web.controllers import groups as groups_controller


def create_blueprint() -> Blueprint:
    """创建 groups Blueprint"""
    bp = Blueprint("groups", __name__)
    bp.add_url_rule("/api/groups", view_func=groups_controller.api_get_groups, methods=["GET"])
    bp.add_url_rule(
        "/api/groups/<int:group_id>",
        view_func=groups_controller.api_get_group,
        methods=["GET"],
    )
    bp.add_url_rule("/api/groups", view_func=groups_controller.api_add_group, methods=["POST"])
    bp.add_url_rule(
        "/api/groups/<int:group_id>",
        view_func=groups_controller.api_update_group,
        methods=["PUT"],
    )
    bp.add_url_rule(
        "/api/groups/<int:group_id>",
        view_func=groups_controller.api_delete_group,
        methods=["DELETE"],
    )
    bp.add_url_rule(
        "/api/groups/<int:group_id>/export",
        view_func=groups_controller.api_export_group,
        methods=["GET"],
    )
    return bp
