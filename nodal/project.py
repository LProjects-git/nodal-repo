"""nodal.project — analyse d'une arborescence complète.

Chaque fichier est analysé séparément, puis les graphes sont fusionnés et
les appels non résolus sont recroisés avec l'index global des définitions :
un appel vers une fonction définie dans un *autre* fichier du projet devient
une vraie arête, au lieu de finir dans les externes.

Ce qui reste dans les externes après fusion est donc soit une bibliothèque
(`std`, `json`, builtins...), soit une définition réellement introuvable —
regroupée sous le nœud `?`.
"""

from __future__ import annotations

from pathlib import Path

from .model import (AnalysisError, Edge, ExternalNode, Graph,
                    drop_deferred, rebuild_members)

DEFAULT_IGNORES = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    "node_modules", "venv", ".venv", "env", "build", "dist", "cmake-build-debug",
    "third_party", "vendor", ".tox", ".idea", ".vscode", "site-packages",
}


def _walk(root: Path, exts: set[str], recursive: bool,
          ignore: set[str], max_files: int) -> list[Path]:
    found: list[Path] = []
    it = root.rglob("*") if recursive else root.glob("*")
    for p in sorted(it):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        if any(part in ignore for part in p.parts):
            continue
        found.append(p)
        if len(found) >= max_files:
            break
    return found


def analyze_dir(root: str | Path, *, lang: str | None = None, recursive: bool = True,
                ignore: set[str] | None = None, max_files: int = 400,
                **kwargs) -> Graph:
    """Analyse tous les fichiers d'un dossier et retourne un graphe unifié.

    `lang` : "python", "cpp" ou None (déduit du contenu du dossier — le
    langage majoritaire l'emporte, pour éviter de mélanger deux graphes).
    Les autres options sont transmises au frontend C++ (`backend`...).
    """
    from . import CPP_EXT, PYTHON_EXT
    from .analyzer import analyze_python
    from .cpp import analyze_cpp

    root = Path(root)
    if not root.is_dir():
        raise AnalysisError(f"Dossier introuvable : {root}")
    ignore = DEFAULT_IGNORES | (ignore or set())

    if lang is None:                                   # langage majoritaire
        py = _walk(root, PYTHON_EXT, recursive, ignore, max_files)
        cpp = _walk(root, CPP_EXT, recursive, ignore, max_files)
        if not py and not cpp:
            raise AnalysisError(
                f"Aucun fichier Python ou C/C++ trouvé dans {root}")
        lang, files = ("python", py) if len(py) >= len(cpp) else ("cpp", cpp)
    else:
        exts = PYTHON_EXT if lang == "python" else CPP_EXT
        files = _walk(root, exts, recursive, ignore, max_files)
        if not files:
            raise AnalysisError(f"Aucun fichier {lang} trouvé dans {root}")

    functions, classes, edges = [], [], []
    externals: dict[str, ExternalNode] = {}
    meta: dict[str, dict] = {}
    skipped: list[str] = []

    for f in files:
        rel = f.relative_to(root).as_posix()
        try:
            g = (analyze_cpp(f, **kwargs) if lang == "cpp" else analyze_python(f))
        except AnalysisError as exc:                   # fichier cassé : on continue
            skipped.append(f"{rel} — {exc}")
            continue

        # Préfixer les identifiants par le fichier pour éviter les collisions.
        remap = {fn.id: f"{rel}::{fn.id}" for fn in g.functions}
        for fn in g.functions:
            fn.id, fn.file = remap[fn.id], rel
            functions.append(fn)
        for c in g.classes:
            c.members = [remap.get(m, m) for m in c.members]
            c.file = rel
            classes.append(c)
        for e in g.edges:
            e.src = remap.get(e.src, e.src)
            e.dst = remap.get(e.dst, e.dst)
            edges.append(e)
        for ext in g.externals:
            cur = externals.get(ext.id)
            if cur is None:
                externals[ext.id] = ext
            else:
                cur.members += [m for m in ext.members if m not in cur.members]
        meta.update({rel: v for v in g.meta.values()} if g.meta else {})

    graph = Graph(path=str(root), functions=functions,
                  externals=list(externals.values()), classes=classes,
                  edges=edges, lang=lang, files=[f.relative_to(root).as_posix()
                                                 for f in files],
                  meta={"root": str(root), "files": meta, "skipped": skipped})
    _link_across_files(graph)
    return rebuild_members(drop_deferred(graph))


def _link_across_files(graph: Graph) -> None:
    """Transforme les appels externes en arêtes réelles quand la définition
    existe dans un autre fichier du projet."""
    by_qual: dict[str, str] = {}      # "module.func" / "Classe.methode" -> id
    by_name: dict[str, list[str]] = {}
    for f in graph.functions:
        stem = Path(f.file).with_suffix("").as_posix().replace("/", ".")
        bare = f.id.split("::", 1)[1]
        by_qual.setdefault(f"{stem}.{bare}", f.id)
        by_qual.setdefault(f"{stem.split('.')[-1]}.{bare}", f.id)
        by_name.setdefault(f.name, []).append(f.id)

    imports = {rel: m.get("imports", {})
               for rel, m in graph.meta.get("files", {}).items()}

    def resolve(edge: Edge) -> str | None:
        if not edge.symbol:
            return None
        src_file = edge.src.split("::", 1)[0]
        sym = edge.symbol
        # Python : suivre l'alias d'import (from utils import helper)
        head, _, rest = sym.partition(".")
        target = imports.get(src_file, {}).get(head)
        if target:
            full = f"{target}.{rest}" if rest else target
            hit = (by_qual.get(full) or by_qual.get(full.lstrip("."))
                   or by_qual.get(f"{full}.__init__"))
            if hit:
                return hit
            # `pkg.mod.Classe.methode` : chercher "Classe.methode" du bon fichier
            parts = full.lstrip(".").split(".")
            if len(parts) >= 2:
                hit = by_qual.get(".".join(parts[-3:])) or \
                    next((i for i in by_name.get(parts[-1], [])
                          if i.split("::", 1)[1].startswith(parts[-2] + ".")), None)
                if hit:
                    return hit
            tail = full.rsplit(".", 1)[-1]
            cands = [i for i in by_name.get(tail, [])
                     if not i.startswith(src_file + "::")]
            if len(cands) == 1:
                return cands[0]
            return None
        # C++ / appel non qualifié : nom unique dans tout le projet
        name = sym.split("::")[-1].split(".")[-1]
        cands = by_name.get(name, [])
        if len(cands) == 1 and not cands[0].startswith(src_file + "::"):
            return cands[0]
        return None

    kept: list[Edge] = []
    linked = 0
    for e in graph.edges:
        if e.external:
            hit = resolve(e)
            if hit:
                kept.append(Edge(src=e.src, dst=hit, lineno=e.lineno, symbol=e.symbol))
                linked += 1
                continue
        kept.append(e)
    graph.edges = kept
    graph.meta["cross_file_links"] = linked

    # purger les externes devenus orphelins
    used = {e.dst for e in graph.edges if e.external}
    graph.externals = [x for x in graph.externals if x.id in used]
