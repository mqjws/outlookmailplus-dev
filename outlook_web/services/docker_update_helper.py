"""Docker API 自更新 — updater 容器入口

该模块用于 A2（按需 helper job 容器）模式：
- 由主应用容器通过 Docker API 临时拉起一个“updater 容器”
- updater 容器负责执行真正的镜像更新流程（pull + create + stop/rename + cleanup）

为什么需要 updater 容器？
- 如果在 app 容器内部执行更新，并在流程中 stop 自己，会导致后续步骤无法继续（进程被杀死）
- 将 stop/rename/cleanup 交给另一个短生命周期容器执行，可以避免“自杀”问题

运行方式：
  python -m outlook_web.services.docker_update_helper

需要的环境变量：
- DOCKER_SELF_UPDATE_ALLOW=true
- DOCKER_UPDATE_TARGET_CONTAINER_ID=<要更新的容器ID>
- DOCKER_UPDATE_REMOVE_OLD=true/false
- DOCKER_UPDATE_START_DELAY_SECONDS=2  # 可选：给 HTTP 响应留时间再开始 stop
"""

from __future__ import annotations

import os
import sys
import time


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def main() -> int:
    target_id = os.getenv("DOCKER_UPDATE_TARGET_CONTAINER_ID", "").strip()
    if not target_id:
        print("Missing env DOCKER_UPDATE_TARGET_CONTAINER_ID", file=sys.stderr)
        return 2

    remove_old = _get_bool("DOCKER_UPDATE_REMOVE_OLD", False)

    try:
        delay = int(os.getenv("DOCKER_UPDATE_START_DELAY_SECONDS", "2").strip() or "2")
    except Exception:
        delay = 2

    # 给触发更新的 HTTP 响应留出时间（尤其是 app 先返回，再由 updater stop app）
    if delay > 0:
        time.sleep(delay)

    try:
        from outlook_web.services import docker_update

        result = docker_update.self_update(
            remove_old=remove_old,
            target_container_id=target_id,
        )
        success = bool(result.get("success"))
        # updater 容器的 stdout/stderr 可用于排障；主容器默认 auto_remove
        print(result)
        return 0 if success else 1
    except Exception as e:
        print(f"Update helper failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
