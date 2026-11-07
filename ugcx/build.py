"""Pipeline : référentiel des cinémas (resolve) puis séances (scrape)."""

from __future__ import annotations

import json
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import allocine, geo, match, ugc
from .http import Http

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PUBLIC = ROOT / "docs" / "data"
PARIS = ZoneInfo("Europe/Paris")
MIN_CINEMAS = 30  # en dessous, on considère que la page UGC a changé de forme


def now() -> str:
    return datetime.now(PARIS).isoformat(timespec="seconds")


def _load(path: Path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _dump(path: Path, obj, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=1)
    path.write_text(text + "\n", "utf-8")


# --- 1. Référentiel ------------------------------------------------------

def resolve(http: Http | None = None) -> list[dict]:
    http = http or Http()
    previous = {c["id"]: c for c in _load(DATA / "cinemas.json", {}).get("cinemas", [])}
    overrides = _load(DATA / "overrides.json", {})

    page = ugc.fetch(http)
    _dump_text(DATA / "debug" / "ugc-cinemas.html", page)
    cinemas = ugc.parse(page)
    for extra in overrides.get("extra", []):
        cinemas.append(extra)
    if len(cinemas) < MIN_CINEMAS:
        raise SystemExit(
            f"Seulement {len(cinemas)} cinémas lus sur ugc.fr : la page a sans doute changé. "
            "On garde l'ancien référentiel (voir data/debug/ugc-cinemas.html)."
        )
    skip = set(overrides.get("exclude", []))
    cinemas = [c for c in cinemas if c["id"] not in skip]

    # Géocodage (avec cache sur le référentiel précédent)
    for c in cinemas:
        ov = overrides.get("cinemas", {}).get(c["id"], {})
        prev = previous.get(c["id"], {})
        if ov.get("lat"):
            c["lat"], c["lon"] = ov["lat"], ov["lon"]
        elif prev.get("lat") and prev.get("address") == c["address"]:
            c["lat"], c["lon"] = prev["lat"], prev["lon"]
        else:
            ll = geo.geocode(http, c["address"], c["postcode"], c["city"])
            c["lat"], c["lon"] = ll if ll else (None, None)

    # Salles AlloCiné des départements concernés
    depts = sorted({c["dept"] for c in cinemas if c.get("dept")})
    dept_ids = allocine.departement_ids(http)
    log.info("AlloCiné : %d départements repérés, %d utiles", len(dept_ids), len(depts))
    theaters: list[dict] = []
    for d in depts:
        loc = dept_ids.get(d)
        if not loc:
            log.warning("Département %s introuvable sur AlloCiné", d)
            continue
        ts = allocine.theaters(http, loc)
        log.info("  %s (%s) : %d salles", d, loc, len(ts))
        theaters.extend(ts)
    _dump(DATA / "allocine_theaters.json", {"fetchedAt": now(), "theaters": theaters})

    # Association
    by_id = {t["id"]: t for t in theaters}
    forced = {ov["allocine"] for ov in overrides.get("cinemas", {}).values() if ov.get("allocine")}
    auto = match.assign([c for c in cinemas if "allocine" not in overrides.get("cinemas", {}).get(c["id"], {})],
                        [t for t in theaters if t["id"] not in forced])
    for c in cinemas:
        ov = overrides.get("cinemas", {}).get(c["id"], {})
        if "allocine" in ov:
            c["allocine"] = ov["allocine"]
            c["allocineName"] = by_id.get(ov["allocine"] or "", {}).get("name")
            c["matchScore"] = "manuel"
            continue
        best, s = auto[c["id"]]
        c["allocine"] = best["id"] if best else None
        c["allocineName"] = best["name"] if best else None
        c["matchScore"] = s

    # Dernier recours pour la position : l'adresse AlloCiné de la salle.
    for c in cinemas:
        t = by_id.get(c.get("allocine") or "")
        if c.get("lat") is None and t:
            ll = geo.geocode(http, t["address"].replace(t.get("postcode", ""), " "), t.get("postcode", ""), "")
            if ll:
                c["lat"], c["lon"] = ll

    _dump(DATA / "cinemas.json", {"resolvedAt": now(), "source": ugc.URL, "cinemas": cinemas})
    _write_report(cinemas)
    ok = sum(1 for c in cinemas if c["allocine"])
    log.info("Référentiel : %d cinémas, %d associés à AlloCiné, %d géocodés",
             len(cinemas), ok, sum(1 for c in cinemas if c.get("lat")))
    return cinemas


def _dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def _write_report(cinemas: list[dict]) -> None:
    lines = ["# Rapport d'association UGC -> AlloCiné", "", f"Généré le {now()}", ""]
    missing = [c for c in cinemas if not c.get("allocine")]
    doubtful = [c for c in cinemas if c.get("allocine") and isinstance(c.get("matchScore"), float)
                and c["matchScore"] < 0.8]
    nogeo = [c for c in cinemas if not c.get("lat")]
    lines += [f"- Cinémas : {len(cinemas)}", f"- Non associés : {len(missing)}",
              f"- Associations à vérifier (score < 0,8) : {len(doubtful)}",
              f"- Non géocodés : {len(nogeo)}", ""]
    if missing:
        lines += ["## Non associés", "", "| id | nom | adresse | meilleur score |", "|---|---|---|---|"]
        lines += [f"| `{c['id']}` | {c['name']} | {c['address']} {c['postcode']} {c['city']} | {c['matchScore']} |"
                  for c in missing]
        lines.append("")
    if doubtful:
        lines += ["## À vérifier", "", "| id | nom UGC | salle AlloCiné | score |", "|---|---|---|---|"]
        lines += [f"| `{c['id']}` | {c['name']} | {c['allocineName']} ({c['allocine']}) | {c['matchScore']} |"
                  for c in doubtful]
        lines.append("")
    lines += ["Pour corriger : `data/overrides.json` -> "
              '`{"cinemas": {"<id>": {"allocine": "C0XXX"}}}` (ou `null` pour ignorer).', ""]
    (DATA / "report.md").write_text("\n".join(lines), "utf-8")


# --- 2. Séances ----------------------------------------------------------

def _scrape_one(c: dict, days: list[date]) -> tuple[dict, dict, dict]:
    http = Http()
    movies: dict[str, dict] = {}
    per_day: dict[str, list] = {}
    errors = 0
    for d in days:
        try:
            raw = allocine.showtimes_raw(http, c["allocine"], d)
        except Exception as exc:
            log.warning("%s %s : %s", c["name"], d, exc)
            errors += 1
            continue
        m, shows = allocine.compact_showtimes(raw)
        movies.update(m)
        if shows:
            per_day[d.isoformat()] = shows
    return c, movies, {"days": per_day, "errors": errors}


def scrape(days: int = 7, workers: int = 3, limit: int | None = None) -> None:
    ref = _load(DATA / "cinemas.json", None)
    if not ref:
        raise SystemExit("Pas de data/cinemas.json : lancer d'abord `python -m ugcx resolve`.")
    cinemas = [c for c in ref["cinemas"] if c.get("allocine")]
    if limit:
        cinemas = cinemas[:limit]
    today = datetime.now(PARIS).date()
    day_list = [today + timedelta(days=i) for i in range(days)]

    tmp = PUBLIC / "showtimes.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    all_movies: dict[str, dict] = {}
    stats = {"cinemas": 0, "withShows": 0, "shows": 0, "errors": 0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for c, movies, res in pool.map(lambda c: _scrape_one(c, day_list), cinemas):
            all_movies.update(movies)
            n = sum(len(v) for v in res["days"].values())
            stats["cinemas"] += 1
            stats["shows"] += n
            stats["errors"] += res["errors"]
            if n:
                stats["withShows"] += 1
            log.info("%-40s %4d séances", c["name"][:40], n)
            _dump(tmp / f"{c['allocine']}.json", {"days": res["days"]}, compact=True)

    if stats["withShows"] == 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit("Aucune séance récupérée : AlloCiné bloque peut-être. On garde les données précédentes.")

    final = PUBLIC / "showtimes"
    shutil.rmtree(final, ignore_errors=True)
    tmp.rename(final)
    _dump(PUBLIC / "movies.json", all_movies, compact=True)
    _dump(PUBLIC / "cinemas.json", [_public(c) for c in ref["cinemas"]], compact=True)
    _dump(PUBLIC / "meta.json", {
        "updatedAt": now(), "days": [d.isoformat() for d in day_list],
        "resolvedAt": ref.get("resolvedAt"), "movies": len(all_movies), **stats,
    })
    log.info("Séances : %s, %d films", stats, len(all_movies))


def _public(c: dict) -> dict:
    keys = ("id", "name", "group", "address", "postcode", "city", "lat", "lon", "allocine", "ugcUrl")
    return {k: c.get(k) for k in keys}
