"""python -m ugcx {resolve,scrape,all} [--days N] [--limit N]"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta

from . import build


def main() -> None:
    p = argparse.ArgumentParser(prog="ugcx")
    p.add_argument("command", choices=["resolve", "scrape", "all", "auto"],
                   help="auto = resolve si le référentiel a plus de 7 jours, puis scrape")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--limit", type=int, default=None, help="ne traiter que N cinémas (tests)")
    p.add_argument("--workers", type=int, default=3)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname).1s %(message)s")

    if args.command in ("resolve", "all"):
        build.resolve()
    if args.command == "auto":
        ref = build._load(build.DATA / "cinemas.json", {})
        stamp = ref.get("resolvedAt")
        stale = not stamp or datetime.fromisoformat(stamp) < datetime.now(build.PARIS) - timedelta(days=7)
        if stale:
            build.resolve()
    if args.command in ("scrape", "all", "auto"):
        build.scrape(days=args.days, workers=args.workers, limit=args.limit)


if __name__ == "__main__":
    main()
