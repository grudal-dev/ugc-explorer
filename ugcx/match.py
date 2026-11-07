"""Associe chaque cinéma de la liste UGC à sa salle AlloCiné."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .text import norm, tokens

THRESHOLD = 0.55
STREET_WORDS = {"rue", "avenue", "av", "bd", "boulevard", "place", "pl", "allee", "quai", "cours",
                "centre", "commercial", "cc", "zone", "route", "chemin", "impasse", "square", "niveau"}


def _street_numbers(s: str) -> set[str]:
    return set(re.findall(r"\b\d{1,4}\b", norm(s)))


def score(cinema: dict, theater: dict) -> float:
    a, b = tokens(cinema["name"]), tokens(theater["name"])
    # « UGC » et « mk2 » sont présents partout : ils ne départagent rien.
    weak = {"ugc", "mk2", "cite", "pathe", "gaumont", "cgr"}
    a_strong, b_strong = a - weak, b - weak
    jacc = len(a_strong & b_strong) / max(1, len(a_strong | b_strong))
    seq = SequenceMatcher(None, norm(cinema["name"]), norm(theater["name"])).ratio()
    s = 0.55 * jacc + 0.45 * seq
    if cinema.get("postcode") and cinema["postcode"] == theater.get("postcode"):
        s += 0.15
    addr_a, addr_b = tokens(cinema.get("address", "")), tokens(theater.get("address", ""))
    if addr_a and addr_b:
        s += 0.2 * len(addr_a & addr_b) / max(1, len(addr_a))
    nums_a = _street_numbers(cinema.get("address", ""))
    same_num = bool(nums_a and nums_a & _street_numbers(theater.get("address", "")))
    if same_num:
        s += 0.05
    # Même rue (et même numéro) : très bon indice quand les noms diffèrent
    # (« Horizon Grand Écran » = « Limoges Centre », place Denis-Dussoubs).
    street = {t for t in (addr_a & addr_b) - STREET_WORDS if len(t) >= 4 and not t.isdigit()}
    if street and (same_num or len(street) >= 2):
        s += 0.3
    # Marque contradictoire (UGC chez nous, Pathé chez AlloCiné…) : pénalité.
    na, nb = norm(cinema["name"]), norm(theater["name"])
    for brand in ("ugc", "mk2", "pathe", "gaumont", "cgr", "kinepolis", "megarama"):
        if (brand in na.split()) != (brand in nb.split()):
            s -= 0.15
    return round(s, 3)


def candidates(cinema: dict, theaters: list[dict]) -> list[tuple[float, dict]]:
    """Salles du même département, triées par score décroissant.

    On ne se limite pas au code postal : ugc.fr et AlloCiné ne donnent pas
    toujours le même (Lille 59000/59800, Paris 5e/6e…).
    """
    pool = [t for t in theaters if t.get("dept") == cinema.get("dept")] or theaters
    return sorted(((score(cinema, t), t) for t in pool), key=lambda x: -x[0])


def best_match(cinema: dict, theaters: list[dict]) -> tuple[dict | None, float]:
    cands = candidates(cinema, theaters)
    if not cands or cands[0][0] < THRESHOLD:
        return None, cands[0][0] if cands else 0.0
    return cands[0][1], cands[0][0]


def assign(cinemas: list[dict], theaters: list[dict]) -> dict[str, tuple[dict | None, float]]:
    """Association globale : une salle AlloCiné ne sert qu'une fois (meilleurs scores d'abord)."""
    pairs = []
    best_seen: dict[str, float] = {}
    for c in cinemas:
        cands = candidates(c, theaters)
        best_seen[c["id"]] = cands[0][0] if cands else 0.0
        pairs += [(s, c["id"], t) for s, t in cands[:5] if s >= THRESHOLD]
    pairs.sort(key=lambda x: -x[0])
    out: dict[str, tuple[dict | None, float]] = {}
    used: set[str] = set()
    for s, cid, t in pairs:
        if cid in out or t["id"] in used:
            continue
        out[cid] = (t, s)
        used.add(t["id"])
    for c in cinemas:
        out.setdefault(c["id"], (None, best_seen[c["id"]]))
    return out
