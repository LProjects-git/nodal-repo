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
    truncated: bool = False      # source coupée (voir truncate_sources)


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


def layout(graph: Graph, max_depth: int = 14) -> dict[str, int]:
    """Assigne à chaque nœud une couche (colonne) : appelants à gauche,
    appelés à droite, externes tout à droite.

    Le niveau est la distance *la plus courte* depuis une racine, calculée
    en largeur d'abord. Prendre le chemin le plus long produirait, sur un
    graphe réel comportant des cycles, des centaines de niveaux et donc une
    bande horizontale illisible. `max_depth` borne l'étalement.
    """
    from collections import deque

    internal = [e for e in graph.edges if not e.external]
    succ: dict[str, list[str]] = {}
    callees = set()
    for e in internal:
        succ.setdefault(e.src, []).append(e.dst)
        callees.add(e.dst)

    ids = [f.id for f in graph.functions]
    roots = [i for i in ids if i not in callees] or ids[:1]

    depth: dict[str, int] = {r: 0 for r in roots}
    queue = deque(roots)
    while queue:
        nid = queue.popleft()
        d = depth[nid]
        if d >= max_depth:
            continue
        for nxt in succ.get(nid, ()):
            if nxt not in depth:
                depth[nxt] = d + 1
                queue.append(nxt)

    for i in ids:                                  # nœuds isolés ou cycliques
        depth.setdefault(i, 0)
    last = min(max(depth.values(), default=0) + 1, max_depth + 1)
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


def truncate_sources(graph: Graph, max_lines: int) -> Graph:
    """Limite le code embarqué dans chaque nœud.

    Sur un gros projet, le source complet de milliers de fonctions pèse
    l'essentiel du fichier HTML. Les nœuds tronqués sont signalés dans
    l'affichage.
    """
    if max_lines <= 0:
        return graph
    for f in graph.functions:
        lines = f.source.split("\n")
        if len(lines) > max_lines:
            f.source = "\n".join(lines[:max_lines])
            f.truncated = True
    return graph


def subgraph(graph: Graph, focus: str, depth: int = 2,
             direction: str = "both") -> Graph:
    """Ne conserve que le voisinage de `focus` jusqu'à `depth` sauts.

    `focus` correspond à une fonction dont l'identifiant *contient* le texte
    donné (insensible à la casse). `direction` vaut "callees" (ce que la
    fonction appelle), "callers" (qui l'appelle) ou "both".
    """
    seeds = [f.id for f in graph.functions if focus.lower() in f.id.lower()]
    if not seeds:
        raise AnalysisError(
            f"Aucune fonction ne correspond à « {focus} ». "
            f"Exemples disponibles : "
            f"{', '.join(f.name for f in graph.functions[:5])}…")

    out: dict[str, list[str]] = {}
    inn: dict[str, list[str]] = {}
    for e in graph.edges:
        out.setdefault(e.src, []).append(e.dst)
        inn.setdefault(e.dst, []).append(e.src)

    keep = set(seeds)
    frontier = set(seeds)
    for _ in range(max(0, depth)):
        nxt: set[str] = set()
        for nid in frontier:
            if direction in ("callees", "both"):
                nxt |= set(out.get(nid, []))
            if direction in ("callers", "both"):
                nxt |= set(inn.get(nid, []))
        nxt -= keep
        keep |= nxt
        frontier = nxt
        if not frontier:
            break

    graph.functions = [f for f in graph.functions if f.id in keep]
    graph.externals = [x for x in graph.externals if x.id in keep]
    graph.edges = [e for e in graph.edges if e.src in keep and e.dst in keep]
    kept_files = {f.file for f in graph.functions}
    kept_classes = []
    for c in graph.classes:
        c.members = [m for m in c.members if m in keep]
        if c.members:
            kept_classes.append(c)
    graph.classes = kept_classes
    graph.files = [f for f in graph.files if f in kept_files]
    graph.meta["focus"] = {"seed": focus, "matches": len(seeds), "depth": depth}
    return graph


def drop_externals(graph: Graph) -> Graph:
    """Retire tous les nœuds externes (bibliothèques, builtins, introuvables)."""
    ext = {x.id for x in graph.externals}
    graph.externals = []
    graph.edges = [e for e in graph.edges if e.dst not in ext]
    return graph
