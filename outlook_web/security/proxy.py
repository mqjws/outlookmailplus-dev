from __future__ import annotations

import ipaddress

from werkzeug.middleware.proxy_fix import ProxyFix


def is_trusted_proxy(address: str, trusted_proxies: list[str] | tuple[str, ...]) -> bool:
    try:
        parsed_address = ipaddress.ip_address(address)
    except ValueError:
        return False
    for proxy in trusted_proxies:
        try:
            if parsed_address in ipaddress.ip_network(proxy, strict=False):
                return True
        except ValueError:
            continue
    return False


def resolve_forwarded_client_ip(remote_addr: str, forwarded_for: str, trusted_proxies: list[str]) -> str:
    if not is_trusted_proxy(remote_addr, trusted_proxies):
        return remote_addr or "unknown"
    for candidate in reversed(forwarded_for.split(",")):
        candidate = candidate.strip()
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            return remote_addr or "unknown"
        if not is_trusted_proxy(candidate, trusted_proxies):
            return candidate
    return remote_addr or "unknown"


class TrustedProxyFix(ProxyFix):
    def __init__(self, app, trusted_proxies: list[str]):
        if not trusted_proxies:
            raise RuntimeError("PROXY_FIX_ENABLED requires explicit TRUSTED_PROXIES")
        for proxy in trusted_proxies:
            try:
                ipaddress.ip_network(proxy, strict=False)
            except ValueError as exc:
                raise RuntimeError(f"Invalid TRUSTED_PROXIES entry: {proxy}") from exc
        self.trusted_proxies = tuple(trusted_proxies)
        super().__init__(app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)

    def __call__(self, environ, start_response):
        if not is_trusted_proxy(environ.get("REMOTE_ADDR") or "", self.trusted_proxies):
            return self.app(environ, start_response)
        return super().__call__(environ, start_response)
