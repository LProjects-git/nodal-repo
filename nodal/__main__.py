"""CLI : python -m nodal fichier.py [-o sortie.html]"""

from __future__ import annotations

import argparse
import sys

from . import AnalysisError, render


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="nodal",
        description="Graphe d'appels interactif façon Blender pour un fichier Python.",
    )
    parser.add_argument("source", help="fichier .py à analyser")
    parser.add_argument("-o", "--output", default="graph.html",
                        help="fichier de sortie (.html ou .md, défaut: graph.html)")
    args = parser.parse_args()
    try:
        out = render(args.source, args.output)
    except AnalysisError as exc:
        print(f"nodal: {exc}", file=sys.stderr)
        return 1
    print(f"✓ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
