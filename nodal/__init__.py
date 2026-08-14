"""nodal — visualise le graphe d'appels d'un fichier Python
dans un éditeur de nœuds interactif façon Blender.

Usage :
    import nodal
    nodal.render("mon_script.py", "graphe.html")

Ou en ligne de commande :
    python -m nodal mon_script.py -o graphe.html
"""

from __future__ import annotations

from pathlib import Path

from .analyzer import AnalysisError, Graph, analyze
from .renderer import render_html, render_markdown

__version__ = "1.0.0"
__all__ = ["analyze", "render", "AnalysisError", "Graph"]


def render(source: str | Path, output: str | Path = "graph.html") -> Path:
    """Analyse `source` (fichier .py) et écrit la visualisation dans `output`.

    Le format est déduit de l'extension : `.html` (interactif, défaut)
    ou `.md` (résumé texte). Lève `AnalysisError` en cas de problème.
    """
    graph = analyze(source)
    output = Path(output)
    if output.suffix.lower() == ".md":
        return render_markdown(graph, output)
    return render_html(graph, output)
