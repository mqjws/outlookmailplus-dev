from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from outlook_web.services.temp_mail_provider_base import TempMailProviderBase


_REGISTRY: dict[str, type["TempMailProviderBase"]] = {}


def get_registry_snapshot() -> dict[str, type["TempMailProviderBase"]]:
    return dict(_REGISTRY)
