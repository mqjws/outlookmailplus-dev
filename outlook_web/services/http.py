from __future__ import annotations

from typing import Any

import requests


def get_response_details(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text or response.reason
