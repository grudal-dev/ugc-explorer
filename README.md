# ugc-explorer

Quels films puis-je voir **avec ma carte UGC Illimité** autour de moi ?

Une page web (installable sur téléphone) qui croise :

1. la liste officielle des cinémas acceptant la carte (UGC, mk2 et partenaires) publiée sur
   [ugc.fr](https://www.ugc.fr/cinemas-acceptant-ui.html) ;
2. les séances publiées par AlloCiné (endpoints publics, non officiels) ;
3. la géolocalisation (Géoplateforme IGN) pour filtrer par distance.

Projet indépendant, sans lien avec UGC ni AlloCiné.

## Fonctionnement

```
GitHub Actions (3×/jour)
  └─ python -m ugcx auto
       ├─ resolve  (si le référentiel a plus de 7 jours)
       │    ugc.fr  ──► data/cinemas.json   (+ géocodage, + code AlloCiné de chaque salle)
       │                data/report.md      (salles non associées / douteuses)
       └─ scrape   AlloCiné, 7 jours ──► docs/data/{cinemas,movies,meta}.json
                                         docs/data/showtimes/<codeAlloCiné>.json
GitHub Pages ──► docs/index.html (lit ces JSON, filtre par position, jour, VO…)
```

## Mise en route

1. **Settings → Pages → Source : GitHub Actions** (une fois).
2. **Actions → « Mise à jour des séances » → Run workflow** (commande `all` la première fois).
3. Lire `data/report.md` et corriger les associations dans `data/overrides.json` :

```json
{ "cinemas": { "le-star-67000": { "allocine": "P0115" } } }
```

Le code AlloCiné d'une salle se trouve dans l'URL de sa page de séances
(`allocine.fr/seance/salle_gen_csalle=P0115.html`).

## En local

```bash
pip install -r requirements.txt
python -m pytest -q
python -m ugcx resolve           # référentiel
python -m ugcx scrape --limit 5  # séances de 5 cinémas
python -m http.server -d docs    # puis http://localhost:8000
```

## Limites

- Ni ugc.fr ni AlloCiné ne proposent d'API officielle : si leurs pages changent, la collecte
  s'arrête (les données précédentes sont conservées) et il faut adapter `ugcx/ugc.py` ou
  `ugcx/allocine.py`.
- Avant le mercredi, peu de salles ont publié la semaine suivante.
- Certaines séances (spéciales, opéra, événements) peuvent être exclues de la carte, et certains
  partenaires n'acceptent pas la carte dématérialisée : vérifier auprès de la salle.
