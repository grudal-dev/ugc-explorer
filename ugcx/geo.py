"""Géocodage des adresses via la Géoplateforme de l'IGN (ex-API Adresse, gratuite)."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

ENDPOINTS = [
    "https://data.geopf.fr/geocodage/search",
    "https://api-adresse.data.gouv.fr/search/",
]


def geocode(http, address: str, postcode: str, city: str) -> tuple[float, float] | None:
    # Le filtre par code postal échoue sur les codes CEDEX (92092 La Défense…) :
    # on finit par des requêtes sans filtre.
    queries = [
        (f"{address} {postcode} {city}".strip(), postcode),
        (f"{postcode} {city}".strip(), postcode),
        (f"{address} {city}".strip(), None),
        (city.replace("-", " ").strip(), None),
    ]
    for q, pc in queries:
        if not q:
            continue
        for url in ENDPOINTS:
            params = {"q": q, "limit": 1}
            if pc:
                params["postcode"] = pc
            try:
                resp = http.get(url, params)
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
