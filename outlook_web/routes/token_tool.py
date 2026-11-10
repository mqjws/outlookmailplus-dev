"""OAuth Token 获取工具 — 路由层

独立 Blueprint,通过 OAUTH_TOOL_ENABLED 环境变量条件注册 (app.py)。
纯路由映射,不包含业务逻辑 (分层约束: Routes 禁止导入 services)。

业务背景: PRD docs/PRD/2026-04-12-OAuth-Token获取工具PRD.md (v1.3)
"""

from __future__ import annotations

from flask import Blueprint

from outlook_web.controllers import token_tool as token_tool_controller


def create_blueprint() -> Blueprint:
    """创建 token_tool Blueprint (FD §7.1)

    注意: /token-tool/callback 无 @login_required —
    它运行在 OAuth 弹窗中无法携带 Session; 安全校验通过 controller 层的 state 参数完成。
    """
    bp = Blueprint("token_tool", __name__)

    bp.add_url_rule(
        "/token-tool",
        view_func=token_tool_controller.render_page,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/token-tool/prepare",
        view_func=token_tool_controller.prepare_oauth,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/token-tool/callback",
        view_func=token_tool_controller.handle_callback,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/token-tool/exchange",
        view_func=token_tool_controller.exchange_token,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/token-tool/save",
        view_func=token_tool_controller.save_to_account,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/token-tool/accounts",
        view_func=token_tool_controller.get_account_list,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/token-tool/config",
        view_func=token_tool_controller.get_config,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/token-tool/config",
        endpoint="save_config",
        view_func=token_tool_controller.save_config,
        methods=["POST"],
    )

    return bp
