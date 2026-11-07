"""Associe chaque cinéma de la liste UGC à sa salle AlloCiné."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .text import norm, tokens

THRESHOLD = 0.55


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
    if nums_a and nums_a & _street_numbers(theater.get("address", "")):
        s += 0.05
    # Marque contradictoire (UGC chez nous, Pathé chez AlloCiné…) : pénalité.
    na, nb = norm(cinema["name"]), norm(theater["name"])
    for brand in ("ugc", "mk2", "pathe", "gaumont", "cgr", "kinepolis", "megarama"):
        if (brand in na.split()) != (brand in nb.split()):
            s -= 0.15
    return round(s, 3)


def best_match(cinema: dict, theaters: list[dict]) -> tuple[dict | None, float]:
    pool = [t for t in theaters if t.get("postcode") == cinema.get("postcode")]
    pool = pool or [t for t in theaters if t.get("dept") == cinema.get("dept")]
    best, best_s = None, 0.0
    for t in pool:
        s = score(cinema, t)
        if s > best_s:
            best, best_s = t, s
    if best_s < THRESHOLD:
        return None, best_s
    return best, best_s
