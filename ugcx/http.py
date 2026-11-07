"""Client HTTP poli : une requête à la fois, petite pause, quelques tentatives.

On imite un vrai navigateur avec curl_cffi : ugc.fr et allocine.fr filtrent
les clients HTTP « nus ».
"""

from __future__ import annotations

import logging
import time

from curl_cffi import requests

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class Http:
    def __init__(self, delay: float = 0.35, retries: int = 4, timeout: int = 30):
        self.session = requests.Session(impersonate="chrome")
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.count = 0

    def get(self, url: str, params: dict | None = None, **kw) -> requests.Response:
        last_exc: Exception | None = None
        resp = None
        for attempt in range(self.retries):
            time.sleep(self.delay)
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout, **kw)
                self.count += 1
            except Exception as exc:  # erreurs réseau, timeouts
                last_exc = exc
                log.warning("GET %s : %s (tentative %d)", url, exc, attempt + 1)
                time.sleep(3 * (attempt + 1))
                continue
            if resp.status_code in RETRY_STATUS:
                log.warning("GET %s : HTTP %s (tentative %d)", url, resp.status_code, attempt + 1)
                time.sleep(5 * (attempt + 1))
                continue
            return resp
        if resp is not None:
            return resp
        raise RuntimeError(f"GET {url} impossible") from last_exc
