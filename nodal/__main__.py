"""CLI : python -m nodal fichier.(py|cpp) [-o sortie.html]"""

from __future__ import annotations

import argparse
import sys

from . import CPP_EXT, PYTHON_EXT, AnalysisError, render


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="nodal",
        description="Graphe d'appels interactif façon éditeur de nœuds, "
                    "pour du Python ou du C/C++.",
    )
    parser.add_argument("source", help=f"fichier source ({', '.join(sorted(PYTHON_EXT | CPP_EXT))})")
    parser.add_argument("-o", "--output", default="graph.html",
                        help="sortie .html (interactif) ou .md (résumé) [graph.html]")
    parser.add_argument("--backend", choices=["scanner", "clang", "auto"],
                        default="scanner",
                        help="C++ uniquement : moteur d'analyse [scanner]")
    parser.add_argument("--clang-arg", action="append", default=[], metavar="OPT",
                        help="C++/clang : option de compilation, répétable "
                             "(ex. --clang-arg=-Iinclude)")
    args = parser.parse_args()

    kwargs = {}
    if args.source.lower().endswith(tuple(CPP_EXT)):
        kwargs = {"backend": args.backend, "clang_args": args.clang_arg}
    try:
        out = render(args.source, args.output, **kwargs)
    except AnalysisError as exc:
        print(f"nodal: {exc}", file=sys.stderr)
        return 1
    print(f"✓ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
