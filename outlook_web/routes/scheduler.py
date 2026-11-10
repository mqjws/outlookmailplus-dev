from __future__ import annotations

from flask import Blueprint

from outlook_web.controllers import scheduler as scheduler_controller


def create_blueprint() -> Blueprint:
    """创建 scheduler Blueprint"""
    bp = Blueprint("scheduler", __name__)
    bp.add_url_rule(
        "/api/scheduler/status",
        view_func=scheduler_controller.api_get_scheduler_status,
        methods=["GET"],
    )
    return bp
