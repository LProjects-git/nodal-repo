"""nodal.model — structures partagées par tous les frontends (Python, C++)."""

from __future__ import annotations

from dataclasses import dataclass, field


class AnalysisError(Exception):
    """Erreur d'analyse lisible (fichier introuvable, syntaxe invalide...)."""


@dataclass
class FuncNode:
    """Une fonction, méthode ou fonction libre définie dans le fichier."""
    id: str                      # "func", "Classe.methode", "ns::func"
    name: str
    kind: str                    # "function" | "method"
    cls: str | None              # classe/struct englobante
    lineno: int
    source: str
    signature: str
    file: str = ""               # chemin relatif (projets multi-fichiers)


@dataclass
class ExternalNode:
    """Symbole appelé mais non défini dans le fichier (module, header, builtin)."""
    id: str                      # "ext:std"
    name: str
    members: list[str] = field(default_factory=list)
    kind: str = "module"         # module | builtin | unknown


@dataclass
class Edge:
    """Un appel : `src` appelle `dst` à la ligne `lineno`."""
    src: str
    dst: str
    lineno: int
    external: bool = False
    symbol: str = ""             # nom appelé, pour la résolution inter-fichiers


@dataclass
class ClassGroup:
    name: str
    lineno: int
    members: list[str] = field(default_factory=list)
    stereotype: str = "class"    # class | struct | namespace
    file: str = ""


@dataclass
class Graph:
    path: str
    functions: list[FuncNode]
    externals: list[ExternalNode]
    classes: list[ClassGroup]
    edges: list[Edge]
    lang: str = "python"         # pilote la coloration côté HTML
    files: list[str] = field(default_factory=list)   # fichiers analysés
    meta: dict = field(default_factory=dict)         # imports/includes par fichier


def layout(graph: Graph) -> dict[str, int]:
    """Assigne à chaque nœud une couche (colonne) : appelants à gauche,
    appelés à droite, externes tout à droite."""
    internal = [e for e in graph.edges if not e.external]
    callees = {e.dst for e in internal}
    depth: dict[str, int] = {}

    def walk(nid: str, d: int, trail: frozenset[str]) -> None:
        if nid in trail or depth.get(nid, -1) >= d:
            return
        depth[nid] = d
        for e in internal:
            if e.src == nid:
                walk(e.dst, d + 1, trail | {nid})

    roots = [f.id for f in graph.functions if f.id not in callees] or \
            [f.id for f in graph.functions[:1]]
    for r in roots:
        walk(r, 0, frozenset())
    for f in graph.functions:
        depth.setdefault(f.id, 0)
    last = max(depth.values(), default=0) + 1
    for ext in graph.externals:
        depth[ext.id] = last
    return depth


def drop_deferred(graph: Graph) -> Graph:
    """Supprime les arêtes « différées » restées non résolues.

    Un appel de méthode sur un type dont la définition n'est pas visible
    (`std::ifstream f; f.good()`) est émis comme différé : utile à relier
    dans un projet multi-fichiers, pur bruit dans un fichier isolé.
    """
    deferred = {x.id for x in graph.externals if x.kind == "deferred"}
    if not deferred:
        return graph
    graph.edges = [e for e in graph.edges if e.dst not in deferred]
    graph.externals = [x for x in graph.externals if x.id not in deferred]
    return graph


def rebuild_members(graph: Graph) -> Graph:
    """Recalcule la liste des membres de chaque nœud externe à partir des
    arêtes survivantes (après résolution inter-fichiers)."""
    kept: dict[str, list[str]] = {}
    for e in graph.edges:
        if not e.external or not e.symbol:
            continue
        node = next((x for x in graph.externals if x.id == e.dst), None)
        if node is None:
            continue
        member = e.symbol
        for sep in ("::", "."):
            prefix = node.name + sep
            if member.startswith(prefix):
                member = member[len(prefix):]
                break
        lst = kept.setdefault(e.dst, [])
        if member and member not in lst:
            lst.append(member)
    for x in graph.externals:
        x.members = kept.get(x.id, x.members)
    return graph
