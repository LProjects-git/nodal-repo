"""CLI : python -m nodal <fichier|dossier> [-o sortie.html]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import CPP_EXT, PYTHON_EXT, AnalysisError, analyze
from .model import drop_externals, subgraph, truncate_sources
from .renderer import render_html, render_markdown


def _symbols() -> tuple[str, str, str]:
    """Symboles d'affichage compatibles avec la console courante.

    Les consoles Windows (cp1252, cp437) ne savent pas encoder ✓ / ⚠ / — .
    On conserve l'encodage de la console — la forcer en UTF-8 produirait du
    charabia — mais on neutralise l'erreur et on retombe sur de l'ASCII.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")     # jamais d'UnicodeEncodeError
        except (AttributeError, OSError, ValueError):
            pass
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "✓⚠—".encode(enc)
        return "✓", "⚠", "—"
    except (UnicodeEncodeError, LookupError):
        return "OK", "!", "-"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="nodal",
        description="Graphe d'appels interactif façon éditeur de nœuds, "
                    "pour un fichier ou un projet entier (Python / C++).",
    )
    parser.add_argument("source", help="fichier source ou dossier de projet")
    parser.add_argument("-o", "--output", default="graph.html",
                        help="sortie .html (interactif) ou .md (résumé) [graph.html]")
    parser.add_argument("--lang", choices=["python", "cpp"],
                        help="dossier : forcer le langage (défaut : majoritaire)")
    parser.add_argument("--no-recursive", action="store_true",
                        help="dossier : ne pas descendre dans les sous-dossiers")
    parser.add_argument("--ignore", action="append", default=[], metavar="NOM",
                        help="dossier : nom à ignorer, répétable (ex. --ignore=tests)")
    parser.add_argument("--max-files", type=int, default=400, metavar="N",
                        help="dossier : plafond de fichiers analysés [400]")
    parser.add_argument("--backend", choices=["scanner", "clang", "auto"],
                        default="scanner", help="C++ : moteur d'analyse [scanner]")
    parser.add_argument("--clang-arg", action="append", default=[], metavar="OPT",
                        help="C++/clang : option de compilation, répétable")
    grp = parser.add_argument_group("alléger un gros graphe")
    grp.add_argument("--focus", metavar="NOM",
                     help="ne garder que le voisinage des fonctions dont le nom "
                          "contient NOM")
    grp.add_argument("--depth", type=int, default=2, metavar="N",
                     help="avec --focus : nombre de sauts conservés [2]")
    grp.add_argument("--direction", choices=["both", "callees", "callers"],
                     default="both",
                     help="avec --focus : sens du parcours [both]")
    grp.add_argument("--no-externals", action="store_true",
                     help="masquer bibliothèques, builtins et introuvables")
    grp.add_argument("--max-lines", type=int, default=40, metavar="N",
                     help="lignes de code embarquées par nœud, 0 = tout [40]")
    args = parser.parse_args()
    ok, warn_sym, dash = _symbols()

    src = Path(args.source)
    kwargs: dict = {}
    if src.is_dir():
        kwargs = {"lang": args.lang, "recursive": not args.no_recursive,
                  "ignore": set(args.ignore), "max_files": args.max_files}
    if src.is_dir() or src.suffix.lower() in CPP_EXT:
        kwargs |= {"backend": args.backend, "clang_args": args.clang_arg}

    try:
        graph = analyze(src, **kwargs)
    except AnalysisError as exc:
        print(f"nodal: {exc}", file=sys.stderr)
        return 1

    try:
        if args.focus:
            graph = subgraph(graph, args.focus, args.depth, args.direction)
    except AnalysisError as exc:
        print(f"nodal: {exc}", file=sys.stderr)
        return 1
    if args.no_externals:
        graph = drop_externals(graph)
    graph = truncate_sources(graph, args.max_lines)

    out = Path(args.output)
    out = (render_markdown if out.suffix.lower() == ".md" else render_html)(graph, out)

    n_ext = sum(1 for e in graph.edges if e.external)
    print(f"{ok} {out}  {dash}  {len(graph.functions)} fonctions, "
          f"{len(graph.edges) - n_ext} appels internes, {n_ext} externes")
    if len(graph.files) > 1:
        linked = graph.meta.get("cross_file_links", 0)
        print(f"  {len(graph.files)} fichiers, {linked} appels reliés entre fichiers")
    unknown = next((x for x in graph.externals if x.kind == "unknown"), None)
    if unknown:
        preview = ", ".join(unknown.members[:5])
        more = "…" if len(unknown.members) > 5 else ""
        print(f"  {warn_sym} {len(unknown.members)} définitions introuvables : "
              f"{preview}{more}")
    for warn in graph.meta.get("skipped", []):
        print(f"  {warn_sym} ignoré : {warn}", file=sys.stderr)

    total = len(graph.functions) + len(graph.externals)
    if total > 400 and not args.focus:
        print(f"  {warn_sym} {total} nœuds : l'affichage sera dense. Pour cibler,")
        print(f"     --focus <nom_de_fonction> --depth 2, ou --no-externals,")
        print(f"     ou pointez un sous-dossier précis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
