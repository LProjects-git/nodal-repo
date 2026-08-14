"""nodal — visualise le graphe d'appels d'un fichier source
dans un éditeur de nœuds interactif façon Blender.

Langages : Python (.py) et C/C++ (.cpp .cc .cxx .hpp .h .hxx).

Usage :
    import nodal
    nodal.render("mon_script.py", "graphe.html")
    nodal.render("moteur.cpp", "graphe.html")

Ligne de commande :
    python -m nodal moteur.cpp -o graphe.html
"""

from __future__ import annotations

from pathlib import Path

from .analyzer import analyze_python
from .cpp import analyze_cpp
from .project import analyze_dir
from .model import (AnalysisError, ClassGroup, Edge, ExternalNode,
                    FuncNode, Graph, drop_deferred)
from .renderer import render_html, render_markdown

__version__ = "2.0.0"
__all__ = [
    "analyze", "render", "analyze_python", "analyze_cpp", "analyze_dir",
    "AnalysisError", "Graph", "FuncNode", "ClassGroup", "Edge", "ExternalNode",
]

PYTHON_EXT = {".py", ".pyw"}
CPP_EXT = {".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx", ".h", ".c"}


def analyze(source: str | Path, **kwargs) -> Graph:
    """Analyse un fichier *ou un dossier* et retourne son graphe d'appels.

    Pour un dossier, tous les fichiers sont analysés puis reliés entre eux
    (voir `analyze_dir`). Le langage est déduit de l'extension ou du contenu
    du dossier. Les options supplémentaires (`backend`, `clang_args`,
    `recursive`, `ignore`, `max_files`) sont transmises selon le cas.
    """
    if Path(source).is_dir():
        return analyze_dir(source, **kwargs)
    for key in ("lang", "recursive", "ignore", "max_files"):
        kwargs.pop(key, None)                # options propres aux dossiers
    suffix = Path(source).suffix.lower()
    if suffix in PYTHON_EXT:
        return analyze_python(source)
    if suffix in CPP_EXT:
        return drop_deferred(analyze_cpp(source, **kwargs))
    raise AnalysisError(
        f"Extension non prise en charge : '{suffix or Path(source).name}'. "
        f"Attendu : {', '.join(sorted(PYTHON_EXT | CPP_EXT))}"
    )


def render(source: str | Path, output: str | Path = "graph.html", **kwargs) -> Path:
    """Analyse `source` et écrit la visualisation dans `output`.

    Format déduit de l'extension de sortie : `.html` (interactif, défaut)
    ou `.md` (résumé texte). Lève `AnalysisError` en cas de problème.
    """
    graph = analyze(source, **kwargs)
    output = Path(output)
    if output.suffix.lower() == ".md":
        return render_markdown(graph, output)
    return render_html(graph, output)
