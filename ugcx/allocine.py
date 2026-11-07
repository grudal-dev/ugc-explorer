"""Endpoints publics (non officiels) d'AlloCiné : salles et séances.

- /salle/                                   -> liens vers les départements
- /salle/cinema/departement-<id>/?page=N    -> cartes « theater-card » (JSON dans data-theater)
- /_/showtimes/theater-<id>/d-<YYYY-MM-DD>/p-<N>/  -> JSON des films et séances du jour
"""

from __future__ import annotations

import html as htmllib
import json
import logging
import re
from datetime import date

from bs4 import BeautifulSoup

from .text import DEPARTEMENTS, POSTCODE_RE, departement, norm

log = logging.getLogger(__name__)

BASE = "https://www.allocine.fr"


# --- Salles --------------------------------------------------------------

def departement_ids(http) -> dict[str, str]:
    """{code département INSEE: identifiant de page AlloCiné (« departement-83191 »)}."""
    resp = http.get(f"{BASE}/salle/")
    resp.raise_for_status()
    return parse_departement_links(resp.text)


def parse_departement_links(page_html: str) -> dict[str, str]:
    by_name = {norm(v): k for k, v in DEPARTEMENTS.items()}
    out: dict[str, str] = {}
    soup = BeautifulSoup(page_html, "html.parser")
    for a in soup.find_all("a", href=True):
        m = re.search(r"/salle/cinema/((?:departement|ville)-\d+)/?", a["href"])
        if not m:
            continue
        label = norm(a.get("title") or a.get_text(" "))
        label = re.sub(r"^(cinemas?|seances?) (a |en |dans l |dans le |dans la )?", "", label)
        code = by_name.get(label)
        if code and (code not in out or m.group(1).startswith("departement")):
            out[code] = m.group(1)
    return out


def theaters(http, location_id: str, max_pages: int = 40) -> list[dict]:
    """Toutes les salles d'une page de localisation AlloCiné (toutes pages)."""
    found: dict[str, dict] = {}
    for page in range(1, max_pages + 1):
        resp = http.get(f"{BASE}/salle/cinema/{location_id}/", {"page": page} if page > 1 else None)
        if resp.status_code != 200:
            break
        cards = parse_theater_cards(resp.text)
        new = [t for t in cards if t["id"] not in found]
        for t in cards:
            found.setdefault(t["id"], t)
        if not new:
            break
    return list(found.values())


_ADDR_RE = re.compile(r"<address[^>]*>(.*?)</address>", re.S)


def parse_theater_cards(page_html: str) -> list[dict]:
    out = []
    for chunk in page_html.split("theater-card")[1:]:
        m = re.search(r'data-theater="([^"]+)"', chunk)
        if not m:
            continue
        try:
            data = json.loads(htmllib.unescape(m.group(1)))
        except json.JSONDecodeError:
            continue
        tid = data.get("id") or data.get("internalId")
        if not tid or not data.get("name"):
            continue
        address = ""
        if a := _ADDR_RE.search(chunk):
            address = " ".join(re.sub(r"<[^>]+>", " ", htmllib.unescape(a.group(1))).split())
        pc = POSTCODE_RE.findall(address)
        out.append({
            "id": str(tid),
            "name": htmllib.unescape(data["name"]),
            "address": address,
            "postcode": pc[-1] if pc else "",
            "dept": departement(pc[-1]) if pc else "",
        })
    return out


# --- Séances -------------------------------------------------------------

def showtimes_raw(http, theater_id: str, day: date) -> list[dict]:
    """Résultats bruts (films + séances) d'une salle pour un jour."""
    results: list[dict] = []
    page = 1
    while True:
        url = f"{BASE}/_/showtimes/theater-{theater_id}/d-{day.isoformat()}/"
        if page > 1:
            url += f"p-{page}/"
        resp = http.get(url)
        if resp.status_code == 404:
            return results
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            return results  # pas de séance ce jour-là
        results.extend(data.get("results") or [])
        total = int((data.get("pagination") or {}).get("totalPages") or 1)
        if page >= total or page >= 15:
            return results
        page += 1


def _poster(movie: dict) -> str | None:
    p = movie.get("poster")
    if isinstance(p, dict):
        url = p.get("url") or p.get("path")
        if url and url.startswith("/"):
            url = "https://fr.web.img6.acsta.net" + url
        # Vignette 310×420 plutôt que l'affiche pleine résolution.
        if url and "acsta.net/" in url and "acsta.net/c_" not in url:
            url = url.replace("acsta.net/", "acsta.net/c_310_420/", 1)
        return url
    return p if isinstance(p, str) else None


def movie_info(movie: dict) -> dict:
    directors = []
    for c in movie.get("credits") or []:
        if ((c.get("position") or {}).get("name") or "").upper() == "DIRECTOR":
            p = c.get("person") or {}
            n = " ".join(x for x in (p.get("firstName"), p.get("lastName")) if x)
            if n:
                directors.append(n)
    rating = ((movie.get("stats") or {}).get("userRating") or {})
    press = ((movie.get("stats") or {}).get("pressReview") or {})
    release = None
    for r in movie.get("releases") or []:
        d = (r.get("releaseDate") or {}).get("date") if isinstance(r.get("releaseDate"), dict) else r.get("releaseDate")
        if d:
            release = str(d)[:10]
            break
    return {
        "title": movie.get("title"),
        "originalTitle": movie.get("originalTitle"),
        "poster": _poster(movie),
        "runtime": movie.get("runtime"),
        "genres": [g.get("translate") for g in (movie.get("genres") or []) if isinstance(g, dict) and g.get("translate")][:3],
        "directors": directors[:2],
        "rating": rating.get("score"),
        "ratingCount": rating.get("count"),
        "press": press.get("score"),
        "release": release,
        "synopsis": _clean(movie.get("synopsisFull") or movie.get("synopsis")),
    }


def _clean(s):
    if not s or not isinstance(s, str):
        return None
    s = " ".join(re.sub(r"<[^>]+>", " ", htmllib.unescape(s)).split())
    return s[:400]


# Formats utiles à l'utilisateur ; le reste (son 7.1, laser, 4K…) est ignoré.
FORMATS = {
    "F_3D": "3D", "3D": "3D", "F_35MM": "35mm", "F_70MM": "70mm", "IMAX": "IMAX", "F_IMAX": "IMAX",
    "4DX": "4DX", "F_4DX": "4DX", "SCREENX": "ScreenX", "DOLBY_CINEMA": "Dolby Cinema",
    "DOLBY_ATMOS": "Atmos", "ICE": "ICE", "INFINITE": "Infinite", "PLF": "Grand écran",
}

_VERSION = {"ORIGINAL": "VO", "LOCAL": "VF", "DUBBED": "VF", "ORIGINAL_SUBTITLED": "VO"}


def compact_showtimes(results: list[dict]) -> tuple[dict, list[dict]]:
    """-> ({movie_id: info}, [{m, t, v, f, u}]) pour un jour d'une salle."""
    movies: dict[str, dict] = {}
    shows: list[dict] = []
    for r in results:
        movie = r.get("movie") or {}
        mid = str(movie.get("internalId") or movie.get("id") or "")
        if not mid:
            continue
        movies[mid] = movie_info(movie)
        seen: set = set()
        for group in (r.get("showtimes") or {}).values():
            for s in group or []:
                key = s.get("internalId") or s.get("startsAt")
                if key in seen or not s.get("startsAt"):
                    continue
                seen.add(key)
                fmt = []
                for k in ("projection", "experience", "picture", "sound"):
                    v = s.get(k)
                    for x in (v if isinstance(v, list) else [v] if v else []):
                        label = FORMATS.get(str(x).upper())
                        if label and label not in fmt:
                            fmt.append(label)
                url = None
                for t in ((s.get("data") or {}).get("ticketing") or []):
                    if t.get("urls"):
                        url = t["urls"][0]
                        break
                shows.append({
                    "m": mid,
                    "t": s["startsAt"][11:16],
                    "v": _VERSION.get(str(s.get("diffusionVersion") or "").upper(), "VF"),
                    "f": fmt,
                    "u": url,
                })
    shows.sort(key=lambda x: (x["t"], x["m"]))
    return movies, shows
