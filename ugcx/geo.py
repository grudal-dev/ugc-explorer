"""Géocodage des adresses via la Géoplateforme de l'IGN (ex-API Adresse, gratuite)."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

ENDPOINTS = [
    "https://data.geopf.fr/geocodage/search",
    "https://api-adresse.data.gouv.fr/search/",
]


def geocode(http, address: str, postcode: str, city: str) -> tuple[float, float] | None:
    queries = [f"{address} {postcode} {city}".strip(), f"{postcode} {city}".strip()]
    for q in queries:
        for url in ENDPOINTS:
            try:
                resp = http.get(url, {"q": q, "postcode": postcode, "limit": 1})
                if resp.status_code != 200:
                    continue
                feats = resp.json().get("features") or []
            except Exception as exc:
                log.warning("géocodage %r via %s : %s", q, url, exc)
                continue
            if feats:
                lon, lat = feats[0]["geometry"]["coordinates"]
                return round(lat, 6), round(lon, 6)
    return None
