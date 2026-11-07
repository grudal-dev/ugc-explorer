"""Liste des cinémas acceptant la carte UGC Illimité, d'après ugc.fr.

La page https://www.ugc.fr/cinemas-acceptant-ui.html n'a pas d'API : on lit le
HTML. Chaque cinéma y apparaît sous forme de bloc (nom, rue, code postal +
ville), en lien vers sa page pour les UGC, en texte brut pour les partenaires.
Le parseur reste volontairement tolérant : il cherche les blocs « feuilles »
qui contiennent un code postal, quel que soit le balisage exact.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, NavigableString, Tag

from .text import POSTCODE_RE, departement, norm, slug

log = logging.getLogger(__name__)

URL = "https://www.ugc.fr/cinemas-acceptant-ui.html"
BLOCK_TAGS = ["li", "p", "a", "div", "td", "address"]
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5"}


def fetch(http) -> str:
    resp = http.get(URL)
    resp.raise_for_status()
    return resp.text


def _lines(el: Tag) -> list[str]:
    text = el.get_text("\n")
    out = []
    for line in text.split("\n"):
        line = " ".join(line.replace("\xa0", " ").split()).strip(" -–,")
        if line:
            out.append(line)
    return out


def _has_postcode(el: Tag) -> bool:
    return bool(POSTCODE_RE.search(el.get_text(" ")))


def _is_leaf_block(el: Tag) -> bool:
    """Bloc contenant un code postal, sans sous-bloc qui en contienne un aussi."""
    if not _has_postcode(el):
        return False
    for child in el.find_all(BLOCK_TAGS):
        if child is not el and _has_postcode(child):
            # Un lien qui n'enveloppe que le nom ne compte pas comme sous-bloc.
            return False
    return True


def _chunks(lines: list[str]) -> list[list[str]]:
    """Découpe les lignes d'un bloc en fiches, chacune terminée par « CP Ville »."""
    out, cur = [], []
    for line in lines:
        cur.append(line)
        if POSTCODE_RE.search(line):
            out.append(cur)
            cur = []
    return out


def _split_entry(lines: list[str]) -> tuple[str, str, str, str] | None:
    """(nom, adresse, code postal, ville) à partir des lignes d'un bloc."""
    idx = None
    for i in range(len(lines) - 1, -1, -1):
        if POSTCODE_RE.search(lines[i]):
            idx = i
            break
    if idx is None:
        return None
    line = lines[idx]
    m = list(POSTCODE_RE.finditer(line))[-1]
    postcode = m.group(1)
    city = line[m.end():].strip(" ,-–")
    before = line[: m.start()].strip(" ,-–")
    head = lines[:idx] + ([before] if before else [])
    if not head:
        return None
    if len(head) == 1:
        # Tout sur une ligne : « UGC Ciné Cité Bercy 2, cour Saint-Emilion »
        mm = re.match(r"^(.*?\D)\s+(\d+(?:\s?(?:bis|ter))?[\s,].*)$", head[0])
        if mm:
            name, address = mm.group(1), mm.group(2)
        else:
            name, address = head[0], ""
    else:
        name, address = head[0], " ".join(head[1:])
    city = re.sub(r"\s*\(.*?\)\s*$", "", city)  # « Paris (3e) » -> « Paris »
    if city.isupper():
        city = "-".join(w.capitalize() for w in city.lower().split("-"))
        city = " ".join(w if w in ("sur", "en", "le", "la", "les", "de") else w[:1].upper() + w[1:] for w in city.split())
    return name.strip(), address.strip(" ,"), postcode, city.strip()


def _group(name: str, href: str | None) -> str:
    n = norm(name)
    if (href and "cinema-ugc" in href) or n.startswith("ugc"):
        return "UGC"
    if n.startswith("mk2") or n.startswith("mk 2"):
        return "mk2"
    return "Partenaire"


def _zone_for(el: Tag) -> str:
    """Titre de section le plus proche au-dessus du bloc (Paris, Lyon…)."""
    for prev in el.find_all_previous(HEADING_TAGS, limit=1):
        return " ".join(prev.get_text(" ").split())
    return ""


def parse(html: str) -> list[dict]:
    """Balisage réel d'ugc.fr d'abord, parseur générique en secours."""
    cinemas = parse_structured(html)
    if len(cinemas) >= 20:
        return cinemas
    log.warning("Balisage ugc.fr inattendu (%d fiches .item--cinema) : parseur générique", len(cinemas))
    return parse_generic(html)


def _title(s: str) -> str:
    return " ".join(s.split()).strip()


def parse_structured(html: str) -> list[dict]:
    """Fiches `.item--cinema-content` : 1re div = nom, 2e div = rue<br>CP VILLE.

    Elles sont rangées dans des blocs repliables `#classic-rN` (cinémas UGC),
    `#partner-rN` (partenaires) ou `#region-N` (une métropole de province).
    """
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, dict] = {}
    for item in soup.select(".item--cinema-content"):
        divs = item.find_all("div", recursive=False)
        if len(divs) < 2:
            continue
        name = _title(divs[0].get_text(" "))
        parsed = _split_entry([name] + _lines(divs[1]))
        if not parsed:
            continue
        name, address, postcode, city = parsed
        a = item.find_parent("a", href=True)
        href = a["href"] if a else None
        if href and not href.startswith("http"):
            href = "https://www.ugc.fr/" + href.lstrip("/")
        box = item.find_parent(id=re.compile(r"^(classic|partner|region)-"))
        box_id = box["id"] if box else ""
        if box_id.startswith("classic"):
            group = "UGC"
        elif box_id.startswith("partner"):
            group = "mk2" if norm(name).startswith("mk2") else "Partenaire"
        else:
            group = _group(name, href)
        zone = ""
        if box_id.startswith("region"):
            ctl = soup.find("a", attrs={"aria-controls": box_id})
            zone = _title(ctl.get_text(" ")) if ctl else ""
        elif box is not None:
            h2 = box.find_previous("h2")
            zone = _title(h2.get_text(" ")) if h2 else ""
        key = f"{norm(name)}|{postcode}"
        if key in out:
            continue
        out[key] = {
            "id": slug(f"{name} {postcode}"),
            "name": _pretty(name),
            "address": address,
            "postcode": postcode,
            "city": city,
            "dept": departement(postcode),
            "group": group,
            "zone": zone.title() if zone.isupper() else zone,
            "ugcUrl": href if href and "ugc.fr" in href else None,
        }
    cinemas = list(out.values())
    log.info("ugc.fr : %d cinémas lus (%s)", len(cinemas), _counts(cinemas))
    return cinemas


def parse_generic(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for junk in soup.find_all(["script", "style", "noscript", "header", "footer", "nav", "form"]):
        junk.decompose()
    root = soup.find("main") or soup.body or soup

    seen: dict[str, dict] = {}
    done: set[int] = set()
    for leaf in root.find_all(BLOCK_TAGS):
        if not _is_leaf_block(leaf):
            continue
        # Si le bloc ne contient que « 75001 Paris », on remonte d'un ou deux
        # niveaux pour récupérer le nom et la rue.
        el = leaf
        for _ in range(3):
            chunks = _chunks(_lines(el))
            if chunks and all(len(c) > 1 or not POSTCODE_RE.match(c[0]) for c in chunks):
                break
            if el.parent is None or len(el.parent.get_text(" ")) > 1500:
                break
            el = el.parent
        if id(el) in done:
            continue
        done.add(id(el))
        if len(el.get_text(" ")) > 1500:  # paragraphe éditorial, pas une fiche cinéma
            continue
        links = [a for a in ([el] if el.name == "a" else el.find_all("a", href=True)) if a.get("href")]
        for chunk in _chunks(_lines(el)):
            parsed = _split_entry(chunk)
            if not parsed:
                continue
            name, address, postcode, city = parsed
            if len(name) < 2 or len(name) > 90:
                continue
            href = None
            for a in links:
                if norm(name)[:12] and norm(name)[:12] in norm(a.get_text(" ")):
                    href = a["href"]
                    break
            if href is None and len(links) == 1 and len(_chunks(_lines(el))) == 1:
                href = links[0]["href"]
            if href and href.startswith("/"):
                href = "https://www.ugc.fr" + href
            key = f"{norm(name)}|{postcode}"
            if key in seen:
                continue
            seen[key] = {
                "id": slug(f"{name} {postcode}"),
                "name": _pretty(name),
                "address": address,
                "postcode": postcode,
                "city": city,
                "dept": departement(postcode),
                "group": _group(name, href),
                "zone": _zone_for(el),
                "ugcUrl": href if href and "ugc.fr" in href else None,
            }
    cinemas = list(seen.values())
    log.info("ugc.fr : %d cinémas lus (%s)", len(cinemas), _counts(cinemas))
    return cinemas


def _pretty(name: str) -> str:
    """Les partenaires sont en MAJUSCULES sur ugc.fr : on adoucit."""
    if name.isupper() and len(name) > 4:
        words = []
        for w in name.split():
            lw = w.lower()
            if lw in {"mk2", "ugc", "cgr"}:
                words.append(w)
            elif lw in {"de", "du", "des", "la", "le", "les", "et", "d", "l", "sur", "en"} and words:
                words.append(lw)
            else:
                words.append("-".join(p.capitalize() for p in w.split("-")))
        return re.sub(r"\b([LD])'(\w)", lambda m: f"{m.group(1)}'{m.group(2).upper()}", " ".join(words))
    return name


def _counts(cinemas: list[dict]) -> str:
    c: dict[str, int] = {}
    for x in cinemas:
        c[x["group"]] = c.get(x["group"], 0) + 1
    return ", ".join(f"{k} {v}" for k, v in sorted(c.items()))
