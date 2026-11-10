from __future__ import annotations

from flask import Blueprint, jsonify, request

from outlook_web.controllers import plugins as plugins_controller
from outlook_web.security.auth import login_required


def create_blueprint(*, csrf_exempt=None) -> Blueprint:
    bp = Blueprint("plugins", __name__)
    if csrf_exempt:
        csrf_exempt(bp)

    @bp.get("/api/plugins")
    @login_required
    def api_get_plugins():
        result = plugins_controller.api_get_plugins()
        if isinstance(result, tuple):
            body, status = result
            return jsonify(body), status
        return jsonify(result)

    @bp.post("/api/plugins/install")
    @login_required
    def api_install_plugin():
        body = request.get_json(silent=True) or {}
        result = plugins_controller.api_install_plugin(body)
        if isinstance(result, tuple):
            payload, status = result
            return jsonify(payload), status
        return jsonify(result)

    @bp.post("/api/plugins/<name>/uninstall")
    @login_required
    def api_uninstall_plugin(name: str):
        body = request.get_json(silent=True) or {}
        result = plugins_controller.api_uninstall_plugin(name, body)
        if isinstance(result, tuple):
            payload, status = result
            return jsonify(payload), status
        return jsonify(result)

    @bp.get("/api/plugins/<name>/config/schema")
    @login_required
    def api_get_plugin_config_schema(name: str):
        result = plugins_controller.api_get_plugin_config_schema(name)
        if isinstance(result, tuple):
            payload, status = result
            return jsonify(payload), status
        return jsonify(result)

    @bp.get("/api/plugins/<name>/config")
    @login_required
    def api_get_plugin_config(name: str):
        result = plugins_controller.api_get_plugin_config(name)
        if isinstance(result, tuple):
            payload, status = result
            return jsonify(payload), status
        return jsonify(result)

    @bp.post("/api/plugins/<name>/config")
    @login_required
    def api_save_plugin_config(name: str):
        body = request.get_json(silent=True) or {}
        result = plugins_controller.api_save_plugin_config(name, body)
        if isinstance(result, tuple):
            payload, status = result
            return jsonify(payload), status
        return jsonify(result)

    @bp.post("/api/plugins/<name>/test-connection")
    @login_required
    def api_test_plugin_connection(name: str):
        result = plugins_controller.api_test_plugin_connection(name)
        if isinstance(result, tuple):
            payload, status = result
            return jsonify(payload), status
        return jsonify(result)

    return bp
