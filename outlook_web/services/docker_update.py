"""Docker API 自更新服务

通过 Docker API 实现容器自更新功能，作为 Watchtower 的替代方案。

安全要求：
- 默认关闭，需 DOCKER_SELF_UPDATE_ALLOW=true 启用
- 检测 docker.sock 是否可访问
- 校验镜像名白名单（仅允许 guangshanshui/outlook-email-plus）
- 操作前记录审计日志

回滚机制：
- 拉取新镜像前保存旧 digest
- 创建新容器但不立即删除旧容器
- 新容器 healthcheck 通过后才删除旧容器
- 失败时保留旧容器
"""

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# 允许自动更新的镜像白名单
#
# 策略A（生产安全）：彻底禁止本地构建镜像触发 Docker API 更新。
# 因此白名单仅允许官方远程镜像前缀，不再放行本地/无 namespace 的镜像名。
ALLOWED_IMAGE_PREFIXES = [
    "guangshanshui/outlook-email-plus",
    "ghcr.io/zeropointsix/outlook-email-plus",
]


def _looks_like_local_image_ref(image_ref: str) -> bool:
    """基于镜像引用字符串的"本地构建"启发式判断。

    说明：该判断用于给出更明确的错误提示。
    真正的"彻底禁止本地构建"还会结合 RepoDigests 检测（若 docker 可用）。
    """
    ref = (image_ref or "").strip()
    if not ref:
        return True

    lower_ref = ref.lower()

    # 无 namespace（如 outlook-email-plus:latest）通常是本地构建或会落到 Docker Hub library
    # 官方镜像应包含 namespace：guangshanshui/outlook-email-plus
    if "/" not in ref:
        return True

    # 常见本地构建/测试 tag（需排除官方镜像）
    # 注意：官方镜像可能使用 guangshanshui/outlook-email-plus:test 等 tag，不能简单检测 test 关键字
    # 改为：只检测明确的本地构建模式（无 namespace 或非官方 namespace）

    # 提取 namespace 并检查是否为官方来源
    # 对于 Docker Hub 镜像（如 guangshanshui/xxx），namespace 是第一段
    # 对于 GHCR 等 registry 镜像（如 ghcr.io/zeropointsix/xxx），需要匹配前两段
    _OFFICIAL_PREFIXES = [
        "guangshanshui/",
        "docker.io/guangshanshui/",
        "ghcr.io/guangshanshui/",
        "ghcr.io/zeropointsix/",
    ]

    # 如果镜像引用以官方前缀开头，不视为本地构建
    for prefix in _OFFICIAL_PREFIXES:
        if lower_ref.startswith(prefix):
            return False

    # 其他情况（非官方 namespace 或无 namespace）视为本地构建
    return True


def _has_repo_digests(image_id: str) -> Optional[bool]:
    """检查镜像是否具有 RepoDigests。

    - pulled 远程镜像通常会有 RepoDigests
    - 本地 build 的镜像通常 RepoDigests 为空

    Returns:
        True/False: 能确定时返回
        None: 无法判断（例如 docker 不可用/异常）
    """
    if not image_id:
        return None
    try:
        import docker

        client = docker.from_env()
        img = client.images.get(image_id)
        repo_digests = (img.attrs or {}).get("RepoDigests") or []
        return bool(repo_digests)
    except Exception:
        return None


def validate_image_for_update(image_ref: str, *, image_id: Optional[str] = None) -> Tuple[bool, str]:
    """用于“触发更新”链路的镜像校验。

    目标：
    1) 镜像名必须在白名单内
    2) 策略A：禁止本地构建镜像触发更新（尽可能在触发阶段就返回明确错误）
    """
    ok, msg = validate_image_name(image_ref)
    if not ok:
        # 额外：若看起来像本地镜像名，给出更明确的提示
        if _looks_like_local_image_ref(image_ref):
            return (
                False,
                f"检测到本地构建/非官方镜像（{image_ref}），已按安全策略禁止 Docker API 一键更新。请使用官方远程镜像部署（如 guangshanshui/outlook-email-plus:latest）。",
            )
        return ok, msg

    # 彻底禁止本地 build：若能通过 RepoDigests 判断，则强制要求存在 RepoDigests
    has_digests = _has_repo_digests(image_id or "")
    if has_digests is False:
        return (
            False,
            "检测到本地构建镜像（RepoDigests 为空），已按安全策略禁止 Docker API 一键更新。请改用远程镜像部署后再更新。",
        )

    return True, "镜像校验通过"


def is_docker_api_enabled() -> bool:
    """检查是否启用 Docker API 自更新功能"""
    return os.getenv("DOCKER_SELF_UPDATE_ALLOW", "false").lower() == "true"


def check_docker_socket() -> Tuple[bool, str]:
    """检查 docker.sock 是否可访问

    Returns:
        (is_available, message)
    """
    socket_path = "/var/run/docker.sock"

    if not os.path.exists(socket_path):
        return False, f"Docker socket 不存在: {socket_path}"

    if not os.access(socket_path, os.R_OK | os.W_OK):
        return False, f"Docker socket 无读写权限: {socket_path}"

    # 尝试连接 Docker API
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True, "Docker socket 可用"
    except ImportError:
        return False, "缺少 docker 库，请运行: pip install docker"
    except Exception as e:
        return False, f"无法连接 Docker API: {str(e)}"


def validate_image_name(image_name: str) -> Tuple[bool, str]:
    """验证镜像名是否在白名单内

    Args:
        image_name: 镜像名（如 guangshanshui/outlook-email-plus:latest）

    Returns:
        (is_valid, message)
    """
    # 去除 tag/digest 部分进行检查
    # 说明：镜像名可能包含 registry port（如 myreg:5000/repo:tag），不能用 split(':')[0]
    ref = (image_name or "").strip()
    # digest 形式：repo@sha256:...
    if "@" in ref:
        ref = ref.split("@", 1)[0]

    base_image = ref
    # tag 形式：repo:tag（仅当最后一个 ':' 之后不包含 '/' 才视为 tag）
    if ":" in base_image:
        left, right = base_image.rsplit(":", 1)
        if "/" not in right:
            base_image = left

    for allowed_prefix in ALLOWED_IMAGE_PREFIXES:
        if base_image == allowed_prefix or base_image.startswith(allowed_prefix + "/"):
            return True, "镜像名校验通过"

    return False, f"镜像名不在白名单内: {image_name}"


def get_container_info(container_id_or_name: str) -> Optional[Dict[str, Any]]:
    """获取指定容器信息

    Args:
        container_id_or_name: 容器 ID / 短 ID / 名称

    Returns:
        {
            "id": "abc123...",
            "name": "outlook-email-plus",
            "image": "guangshanshui/outlook-email-plus:latest",
            "image_id": "sha256:...",
            "labels": {...},
            "env": {...},
            "volumes": {...},
            "networks": {...},
            "restart_policy": {...}
        }
    """
    try:
        import docker

        client = docker.from_env()
        container = client.containers.get(container_id_or_name)

        # 提取容器配置信息
        inspect_data = container.attrs
        config = inspect_data.get("Config", {})
        host_config = inspect_data.get("HostConfig", {})
        network_settings = inspect_data.get("NetworkSettings", {})

        # volumes/binds：同时兼容 bind mount 与 named volume
        volume_specs: list[str] = []
        try:
            binds = host_config.get("Binds") or []
            for b in binds:
                if isinstance(b, str) and b.strip():
                    volume_specs.append(b.strip())
        except Exception:
            pass

        # docker inspect 的 Mounts 信息更完整（尤其是 named volume）
        try:
            mounts = inspect_data.get("Mounts") or []
            for m in mounts:
                if not isinstance(m, dict):
                    continue
                dest = (m.get("Destination") or "").strip()
                if not dest:
                    continue

                m_type = (m.get("Type") or "").strip().lower()
                # bind：使用 Source（宿主机路径）
                if m_type == "bind":
                    src = (m.get("Source") or "").strip()
                # volume：优先用 Name（volume 名），回退 Source
                elif m_type == "volume":
                    src = (m.get("Name") or m.get("Source") or "").strip()
                else:
                    src = (m.get("Source") or m.get("Name") or "").strip()

                if not src:
                    continue

                mode = "rw" if bool(m.get("RW", True)) else "ro"
                spec = f"{src}:{dest}:{mode}"
                # 去重
                if spec not in volume_specs:
                    volume_specs.append(spec)
        except Exception:
            pass

        # pulled 镜像通常具有 RepoDigests；本地 build 通常为空。
        # 注意：容器 inspect 里通常拿不到 RepoDigests，需要通过 image inspect 获取。
        image_repo_digests: list[str] = []
        try:
            img = client.images.get(inspect_data.get("Image", ""))
            image_repo_digests = (img.attrs or {}).get("RepoDigests") or []
        except Exception:
            image_repo_digests = []

        return {
            "id": container.id,
            "short_id": container.short_id,
            "name": container.name,
            "image": config.get("Image", ""),
            "image_id": inspect_data.get("Image", ""),
            "image_repo_digests": image_repo_digests,
            "labels": config.get("Labels", {}),
            "env": config.get("Env", []),
            "volumes": volume_specs,
            "networks": list(network_settings.get("Networks", {}).keys()),
            "restart_policy": host_config.get("RestartPolicy", {}),
            "ports": host_config.get("PortBindings", {}),
            "working_dir": config.get("WorkingDir", ""),
            "user": config.get("User", ""),
        }

    except Exception as e:
        logger.error(f"获取容器信息失败 ({container_id_or_name}): {str(e)}", exc_info=True)
        return None


def get_current_container_info() -> Optional[Dict[str, Any]]:
    """获取当前容器信息

    优先使用 HOSTNAME（容器短 ID），失败时回退按名称查找。
    """
    # 通过环境变量 HOSTNAME 获取当前容器 ID
    hostname = os.getenv("HOSTNAME", "")
    if hostname:
        info = get_container_info(hostname)
        if info:
            return info

    # 回退：通过常见名称查找
    try:
        import docker

        client = docker.from_env()
        containers = client.containers.list(filters={"name": "outlook-email-plus"})
        if not containers:
            logger.error("未找到当前容器 (HOSTNAME 为空且 name 过滤无结果)")
            return None
        return get_container_info(containers[0].id)
    except Exception as e:
        logger.error(f"获取当前容器信息失败: {str(e)}", exc_info=True)
        return None


def spawn_update_helper_container(
    target_container_id: str,
    *,
    remove_old: bool = False,
    start_delay_seconds: int = 2,
    auto_remove: bool = True,
) -> Tuple[bool, str]:
    """启动一个短生命周期的 updater 容器来执行更新。

    设计目的：避免“容器在内部 stop 自己导致更新流程中断”的问题。

    - app 容器负责：鉴权 + 基本校验 + 创建 updater 容器
    - updater 容器负责：pull 镜像 + 创建新容器 + stop/rename/cleanup 旧容器

    Args:
        target_container_id: 要更新的 app 容器 ID
        remove_old: 是否删除旧容器（默认 False，保留备份）
        start_delay_seconds: updater 启动后等待秒数（给 HTTP 响应留出时间）
        auto_remove: updater 退出后自动删除容器

    Returns:
        (success, message)
    """
    try:
        import docker

        client = docker.from_env()

        # 基本安全提示：此模式要求当前容器具备 docker.sock 权限
        socket_ok, socket_msg = check_docker_socket()
        if not socket_ok:
            return False, socket_msg

        # 避免并发：如果已有 updater 在跑，直接拒绝
        try:
            existing = client.containers.list(
                all=True,
                filters={"label": "outlook_email_plus.update_helper=true"},
            )
            for c in existing:
                try:
                    c.reload()
                    if c.status == "running":
                        return False, "已有更新任务正在运行，请稍后再试"
                except Exception:
                    continue
        except Exception:
            # 如果列举失败，不阻塞主流程（后续创建可能仍会失败并返回异常）
            pass

        target = client.containers.get(target_container_id)
        target_image = target.attrs.get("Config", {}).get("Image", "") if target.attrs else ""
        if not target_image:
            return False, "无法获取目标容器镜像信息"

        valid, msg = validate_image_for_update(
            target_image,
            image_id=(target.attrs.get("Image", "") if target.attrs else ""),
        )
        if not valid:
            return False, msg

        helper_name = f"oep-updater-{int(time.time())}"
        helper_cmd = ["python", "-m", "outlook_web.services.docker_update_helper"]

        helper_env = {
            # updater 容器内部也走同一套安全开关
            "DOCKER_SELF_UPDATE_ALLOW": "true",
            "DOCKER_UPDATE_TARGET_CONTAINER_ID": target_container_id,
            "DOCKER_UPDATE_REMOVE_OLD": "true" if remove_old else "false",
            "DOCKER_UPDATE_START_DELAY_SECONDS": str(int(start_delay_seconds)),
        }

        # 透传 registry 凭证（可选）：避免 updater 容器 pull 私有镜像失败
        # 注意：仅当宿主机/当前容器已配置这些环境变量时才会传递。
        for k in (
            "DOCKER_AUTH_CONFIG",
            "DOCKER_CONFIG",
            "DOCKER_USERNAME",
            "DOCKER_PASSWORD",
        ):
            v = os.getenv(k)
            if v:
                helper_env[k] = v

        helper_labels = {
            "outlook_email_plus.update_helper": "true",
            "outlook_email_plus.target_container_id": target_container_id,
            # 防止 Watchtower（如存在）误更新该容器
            "com.centurylinklabs.watchtower.enable": "false",
        }

        helper_volumes = {
            "/var/run/docker.sock": {
                "bind": "/var/run/docker.sock",
                "mode": "rw",
            }
        }

        # 透传 docker config（可选）：例如挂载 /root/.docker 以支持私有仓库拉取
        docker_cfg = os.getenv("DOCKER_CONFIG", "").strip()
        if docker_cfg and os.path.exists(docker_cfg):
            helper_volumes[docker_cfg] = {"bind": docker_cfg, "mode": "ro"}

        logger.info(f"启动 updater 容器: name={helper_name}, image={target_image}, target={target_container_id[:12]}")

        # detach=True 让请求快速返回；remove/auto_remove 让容器运行完自动清理
        container = client.containers.run(
            image=target_image,
            command=helper_cmd,
            name=helper_name,
            detach=True,
            remove=auto_remove,
            environment=helper_env,
            volumes=helper_volumes,
            labels=helper_labels,
            restart_policy={"Name": "no"},
        )

        return True, f"更新任务已启动: {helper_name} ({container.short_id})"

    except Exception as e:
        logger.error(f"启动 updater 容器失败: {str(e)}", exc_info=True)
        return False, f"启动 updater 容器失败: {str(e)}"


def pull_latest_image(image_name: str) -> Tuple[bool, str, Optional[str]]:
    """拉取最新镜像

    Args:
        image_name: 镜像名（如 guangshanshui/outlook-email-plus:latest）

    Returns:
        (success, message, new_digest)
    """
    try:
        import docker

        client = docker.from_env()

        logger.info(f"开始拉取镜像: {image_name}")

        # 拉取镜像（可能耗时较长）
        image = client.images.pull(image_name)

        # 获取新镜像的 digest
        new_digest = image.id

        logger.info(f"镜像拉取成功: {image_name}, digest: {new_digest}")

        return True, "镜像拉取成功", new_digest

    except Exception as e:
        error_msg = f"拉取镜像失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg, None


def compare_image_digest(current_digest: str, new_digest: str) -> bool:
    """比较镜像 digest 是否相同

    Returns:
        True: 镜像相同（已是最新）
        False: 镜像不同（需要更新）
    """
    return current_digest == new_digest


def create_new_container(
    old_container_info: Dict[str, Any],
    new_image: str,
) -> Tuple[bool, str, Optional[Any]]:
    """创建新容器（复制旧容器配置）

    Args:
        old_container_info: 旧容器信息
        new_image: 新镜像名

    Returns:
        (success, message, new_container)
    """
    try:
        import docker

        client = docker.from_env()

        # 生成新容器名称
        old_name = old_container_info["name"]
        new_name = f"{old_name}_new_{int(time.time())}"

        # 构建容器创建参数
        create_kwargs = {
            "image": new_image,
            "name": new_name,
            "detach": True,
            "labels": old_container_info.get("labels", {}),
            "environment": old_container_info.get("env", []),
            "volumes": _parse_volumes(old_container_info.get("volumes", [])),
            "network": None,  # 创建后单独连接网络
            "restart_policy": old_container_info.get("restart_policy", {}),
            "ports": _parse_ports(old_container_info.get("ports", {})),
            "working_dir": old_container_info.get("working_dir", ""),
            "user": old_container_info.get("user", ""),
        }

        logger.info(f"创建新容器: {new_name}")
        logger.debug(f"容器创建参数: {create_kwargs}")

        # 创建容器（但不启动）
        new_container = client.containers.create(**create_kwargs)

        # 连接到相同的网络
        for network_name in old_container_info.get("networks", []):
            try:
                network = client.networks.get(network_name)
                network.connect(new_container)
                logger.info(f"容器已连接到网络: {network_name}")
            except Exception as e:
                logger.warning(f"连接网络失败 {network_name}: {str(e)}")

        logger.info(f"新容器创建成功: {new_container.short_id}")

        return True, "新容器创建成功", new_container

    except Exception as e:
        error_msg = f"创建新容器失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg, None


def _parse_volumes(volumes: list) -> Dict[str, Dict[str, str]]:
    """解析 volumes 配置

    Args:
        volumes: ["/host/path:/container/path:rw", ...]

    Returns:
        {"/host/path": {"bind": "/container/path", "mode": "rw"}}
    """
    result = {}

    for volume in volumes:
        parts = volume.split(":")
        if len(parts) >= 2:
            host_path = parts[0]
            container_path = parts[1]
            mode = parts[2] if len(parts) >= 3 else "rw"

            result[host_path] = {
                "bind": container_path,
                "mode": mode,
            }

    return result


def _parse_ports(ports: Dict[str, Any]) -> Dict[str, Any]:
    """解析 ports 配置

    Args:
        ports: {"5050/tcp": [{"HostPort": "5050"}]}

    Returns:
        {"5050/tcp": 5050}
    """
    result = {}

    for container_port, bindings in ports.items():
        if bindings and isinstance(bindings, list) and len(bindings) > 0:
            host_port = bindings[0].get("HostPort")
            if host_port:
                result[container_port] = int(host_port)

    return result


def start_new_container(container: Any) -> Tuple[bool, str]:
    """启动新容器

    Args:
        container: Docker container 对象

    Returns:
        (success, message)
    """
    try:
        logger.info(f"启动新容器: {container.short_id}")

        container.start()

        # 等待容器启动（最多 10 秒）
        for i in range(10):
            container.reload()
            if container.status == "running":
                logger.info(f"新容器已启动: {container.short_id}")
                return True, "新容器启动成功"
            time.sleep(1)

        return False, "新容器启动超时"

    except Exception as e:
        error_msg = f"启动新容器失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


def health_check_new_container(container: Any, timeout: int = 30) -> Tuple[bool, str]:
    """健康检查新容器

    Args:
        container: Docker container 对象
        timeout: 超时时间（秒）

    Returns:
        (is_healthy, message)
    """
    try:
        logger.info(f"健康检查新容器: {container.short_id}")

        # 简单检查：容器是否在运行
        start_time = time.time()

        while time.time() - start_time < timeout:
            container.reload()

            # 容器状态检查
            if container.status != "running":
                return False, f"容器状态异常: {container.status}"

            # 如果容器有 healthcheck，检查健康状态
            health = container.attrs.get("State", {}).get("Health", {})
            if health:
                health_status = health.get("Status", "")
                if health_status == "healthy":
                    logger.info("新容器健康检查通过")
                    return True, "健康检查通过"
                elif health_status == "unhealthy":
                    return False, "容器健康检查失败"
            else:
                # 没有 healthcheck，等待 5 秒后视为健康
                if time.time() - start_time > 5:
                    logger.info("新容器无 healthcheck 配置，等待 5 秒后视为健康")
                    return True, "健康检查通过（无 healthcheck 配置）"

            time.sleep(2)

        return False, "健康检查超时"

    except Exception as e:
        error_msg = f"健康检查失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


def stop_old_container(container_id: str) -> Tuple[bool, str]:
    """停止旧容器

    Args:
        container_id: 容器 ID

    Returns:
        (success, message)
    """
    try:
        import docker

        client = docker.from_env()
        container = client.containers.get(container_id)

        logger.info(f"停止旧容器: {container.short_id}")

        container.stop(timeout=10)

        logger.info(f"旧容器已停止: {container.short_id}")

        return True, "旧容器已停止"

    except Exception as e:
        error_msg = f"停止旧容器失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


def rename_containers(old_container_id: str, new_container_id: str) -> Tuple[bool, str]:
    """重命名容器（新容器使用原名称）

    Args:
        old_container_id: 旧容器 ID
        new_container_id: 新容器 ID

    Returns:
        (success, message)
    """
    try:
        import docker

        client = docker.from_env()

        old_container = client.containers.get(old_container_id)
        new_container = client.containers.get(new_container_id)

        old_name = old_container.name
        backup_name = f"{old_name}_backup_{int(time.time())}"

        logger.info(f"重命名旧容器: {old_name} -> {backup_name}")
        old_container.rename(backup_name)

        logger.info(f"重命名新容器: {new_container.name} -> {old_name}")
        new_container.rename(old_name)

        return True, "容器重命名成功"

    except Exception as e:
        error_msg = f"重命名容器失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


def cleanup_old_container(container_id: str, remove: bool = False) -> Tuple[bool, str]:
    """清理旧容器

    Args:
        container_id: 容器 ID
        remove: 是否删除容器（默认 False，仅保留备份）

    Returns:
        (success, message)
    """
    try:
        import docker

        client = docker.from_env()
        container = client.containers.get(container_id)

        if remove:
            logger.info(f"删除旧容器: {container.short_id}")
            container.remove(force=True)
            return True, "旧容器已删除"
        else:
            logger.info(f"保留旧容器作为备份: {container.short_id}")
            return True, "旧容器已保留作为备份"

    except Exception as e:
        error_msg = f"清理旧容器失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


def self_update(
    remove_old: bool = False,
    *,
    target_container_id: Optional[str] = None,
) -> Dict[str, Any]:
    """执行容器自更新

    完整流程：
    1. 安全检查（启用开关、docker.sock 可访问性）
    2. 获取当前容器信息
    3. 验证镜像名白名单
    4. 拉取最新镜像
    5. 比较 digest（相同则跳过）
    6. 创建新容器（复制配置）
    7. 启动新容器
    8. 健康检查
    9. 停止旧容器
    10. 重命名容器
    11. 清理/保留旧容器

    Args:
        remove_old: 是否删除旧容器（默认 False，保留作为备份）

    Returns:
        {
            "success": bool,
            "message": str,
            "steps": [
                {"step": "check_permission", "success": True, "message": "..."},
                ...
            ]
        }
    """
    steps = []

    # Step 1: 安全检查 - 启用开关
    if not is_docker_api_enabled():
        return {
            "success": False,
            "message": "Docker API 自更新功能未启用（需设置 DOCKER_SELF_UPDATE_ALLOW=true）",
            "steps": [
                {
                    "step": "check_permission",
                    "success": False,
                    "message": "Docker API 自更新功能未启用",
                }
            ],
        }

    steps.append(
        {
            "step": "check_permission",
            "success": True,
            "message": "Docker API 自更新功能已启用",
        }
    )

    # Step 2: 安全检查 - docker.sock 可访问性
    socket_ok, socket_msg = check_docker_socket()
    steps.append(
        {
            "step": "check_docker_socket",
            "success": socket_ok,
            "message": socket_msg,
        }
    )

    if not socket_ok:
        return {
            "success": False,
            "message": socket_msg,
            "steps": steps,
        }

    # Step 3: 获取当前容器信息（可指定目标容器）
    current_container = get_container_info(target_container_id) if target_container_id else get_current_container_info()
    if not current_container:
        steps.append(
            {
                "step": "get_container_info",
                "success": False,
                "message": "无法获取当前容器信息",
            }
        )
        return {
            "success": False,
            "message": "无法获取当前容器信息",
            "steps": steps,
        }

    steps.append(
        {
            "step": "get_container_info",
            "success": True,
            "message": f"当前容器: {current_container['name']} ({current_container['short_id']})",
        }
    )

    # Step 4: 验证镜像名白名单 + 禁止本地构建镜像触发更新（策略A）
    current_image = current_container["image"]
    valid_image, validate_msg = validate_image_for_update(
        current_image,
        image_id=(current_container.get("image_id") or ""),
    )
    steps.append(
        {
            "step": "validate_image",
            "success": valid_image,
            "message": validate_msg,
        }
    )

    if not valid_image:
        return {
            "success": False,
            "message": validate_msg,
            "steps": steps,
        }

    # Step 5: 拉取最新镜像
    pull_ok, pull_msg, new_digest = pull_latest_image(current_image)
    steps.append(
        {
            "step": "pull_image",
            "success": pull_ok,
            "message": pull_msg,
        }
    )

    if not pull_ok:
        return {
            "success": False,
            "message": pull_msg,
            "steps": steps,
        }

    # Step 6: 比较 digest
    current_digest = current_container["image_id"]
    is_same = compare_image_digest(current_digest, new_digest)

    if is_same:
        steps.append(
            {
                "step": "compare_digest",
                "success": True,
                "message": "镜像已是最新，无需更新",
            }
        )
        return {
            "success": True,
            "message": "镜像已是最新，无需更新",
            "steps": steps,
        }

    steps.append(
        {
            "step": "compare_digest",
            "success": True,
            "message": f"检测到新版本镜像 (digest 不同)",
        }
    )

    # Step 7: 创建新容器
    create_ok, create_msg, new_container = create_new_container(
        current_container,
        current_image,
    )
    steps.append(
        {
            "step": "create_container",
            "success": create_ok,
            "message": create_msg,
        }
    )

    if not create_ok:
        return {
            "success": False,
            "message": create_msg,
            "steps": steps,
        }

    # Step 8: 停止旧容器（释放 host port，避免新容器启动时端口冲突）
    # docker-compose 常见配置会映射 host 端口（如 5000:5000），无法实现“先起新容器再停旧容器”的无缝切换。
    stop_ok, stop_msg = stop_old_container(current_container["id"])
    steps.append(
        {
            "step": "stop_old_container",
            "success": stop_ok,
            "message": stop_msg,
        }
    )

    if not stop_ok:
        # 旧容器无法停止，则新容器启动必然端口冲突；此时取消更新并清理新容器。
        try:
            new_container.remove(force=True)
        except Exception:
            pass
        return {
            "success": False,
            "message": f"停止旧容器失败，已取消更新: {stop_msg}",
            "steps": steps,
        }

    # Step 9: 启动新容器
    start_ok, start_msg = start_new_container(new_container)
    steps.append(
        {
            "step": "start_container",
            "success": start_ok,
            "message": start_msg,
        }
    )

    if not start_ok:
        # 启动失败：尝试恢复旧容器，并删除新容器
        try:
            import docker

            client = docker.from_env()
            old_c = client.containers.get(current_container["id"])
            old_c.start()
            logger.info("新容器启动失败，已尝试重新启动旧容器")
        except Exception as e:
            logger.error(f"新容器启动失败，恢复旧容器也失败: {str(e)}")

        try:
            new_container.remove(force=True)
            logger.info(f"新容器启动失败，已删除: {new_container.short_id}")
        except Exception as e:
            logger.error(f"删除失败的新容器时出错: {str(e)}")

        return {
            "success": False,
            "message": start_msg,
            "steps": steps,
        }

    # Step 10: 健康检查
    health_ok, health_msg = health_check_new_container(new_container)
    steps.append(
        {
            "step": "health_check",
            "success": health_ok,
            "message": health_msg,
        }
    )

    if not health_ok:
        # 健康检查失败：删除新容器，并尝试恢复旧容器
        try:
            new_container.stop(timeout=5)
        except Exception:
            pass
        try:
            new_container.remove(force=True)
            logger.info(f"新容器健康检查失败，已删除: {new_container.short_id}")
        except Exception as e:
            logger.error(f"删除不健康的新容器时出错: {str(e)}")

        try:
            import docker

            client = docker.from_env()
            old_c = client.containers.get(current_container["id"])
            old_c.start()
            logger.info("新容器健康检查失败，已尝试重新启动旧容器")
        except Exception as e:
            logger.error(f"新容器健康检查失败，恢复旧容器也失败: {str(e)}")

        return {
            "success": False,
            "message": health_msg,
            "steps": steps,
        }

    # Step 11: 重命名容器
    rename_ok, rename_msg = rename_containers(current_container["id"], new_container.id)
    steps.append(
        {
            "step": "rename_containers",
            "success": rename_ok,
            "message": rename_msg,
        }
    )

    if not rename_ok:
        logger.warning(f"重命名容器失败: {rename_msg}")

    # Step 12: 清理旧容器
    cleanup_ok, cleanup_msg = cleanup_old_container(current_container["id"], remove=remove_old)
    steps.append(
        {
            "step": "cleanup_old_container",
            "success": cleanup_ok,
            "message": cleanup_msg,
        }
    )

    # 返回成功结果
    return {
        "success": True,
        "message": "容器自更新完成",
        "new_container_id": new_container.short_id,
        "old_container_id": current_container["short_id"],
        "steps": steps,
    }
