"""nodal.analyzer — analyse statique d'un fichier Python (module `ast`).

Recense fonctions, méthodes *et fonctions imbriquées*, puis construit le
graphe d'appels. Un appel non résolu n'est signalé comme introuvable que
s'il ne s'explique ni par un import, ni par un builtin, ni par une variable
locale ou globale — sinon c'est du bruit (`parts.append`, `m.group`...).
"""

from __future__ import annotations

import ast
import builtins as _builtins
from pathlib import Path

from .model import AnalysisError, ClassGroup, Edge, ExternalNode, FuncNode, Graph

_BUILTINS = set(dir(_builtins))
_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)


# --------------------------------------------------------------------------- #
# Utilitaires AST
# --------------------------------------------------------------------------- #

def _call_target(node: ast.Call) -> tuple[str, ...] | None:
    """Chaîne d'attributs d'un appel : `os.path.join()` -> ("os","path","join").
    Retourne None pour un appel dynamique (`f()()`, `tab[i]()`...)."""
    parts: list[str] = []
    cur: ast.expr = node.func
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return tuple(reversed(parts))
    return None


def _bound_names(node: ast.AST) -> set[str]:
    """Noms liés dans un corps : affectations, annotations, boucles,
    `with ... as`, `except ... as`, compréhensions, walrus, imports locaux."""
    names: set[str] = set()

    def add(target: ast.AST) -> None:
        names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))

    for sub in ast.walk(node):
        if isinstance(sub, ast.Assign):
            for t in sub.targets:
                add(t)
        elif isinstance(sub, (ast.AnnAssign, ast.AugAssign)):
            add(sub.target)
        elif isinstance(sub, (ast.For, ast.AsyncFor, ast.comprehension)):
            add(sub.target)
        elif isinstance(sub, (ast.With, ast.AsyncWith)):
            for item in sub.items:
                if item.optional_vars is not None:
                    add(item.optional_vars)
        elif isinstance(sub, ast.ExceptHandler) and sub.name:
            names.add(sub.name)
        elif isinstance(sub, ast.NamedExpr):
            add(sub.target)
        elif isinstance(sub, ast.arg):
            names.add(sub.arg)
        elif isinstance(sub, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in sub.names)
    return names


class _CallCollector(ast.NodeVisitor):
    """Appels d'une fonction, sans descendre dans ses définitions imbriquées."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], int]] = []
        self._depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._depth == 0:                      # la fonction analysée elle-même
            self._depth += 1
            self.generic_visit(node)
            self._depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef    # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        target = _call_target(node)
        if target:
            self.calls.append((target, node.lineno))
        self.generic_visit(node)


# --------------------------------------------------------------------------- #
# Analyse
# --------------------------------------------------------------------------- #

def analyze_python(path: str | Path) -> Graph:
    """Analyse `path` et retourne le graphe d'appels du fichier."""
    path = Path(path)
    if not path.is_file():
        raise AnalysisError(f"Fichier introuvable : {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise AnalysisError(f"{path} n'est pas un fichier texte UTF-8 ({exc})") from exc
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        raise AnalysisError(
            f"Erreur de syntaxe dans {path.name}, ligne {exc.lineno}: {exc.msg}"
        ) from exc

    lines = text.splitlines()
    functions: dict[str, FuncNode] = {}
    classes: list[ClassGroup] = []
    node_id: dict[int, str] = {}                  # id(nœud AST) -> identifiant
    nested: dict[str, dict[str, str]] = {}        # parent -> {nom: identifiant}
    parent_of: dict[str, str | None] = {}         # identifiant -> parent lexical
    ast_of: dict[str, ast.AST] = {}
    class_names: set[str] = set()

    # --- passe 1 : recenser les définitions, imbriquées comprises ---------- #
    def register(fn, cls: str | None, parent: str | None) -> str:
        fid = f"{parent}.{fn.name}" if parent else (
            f"{cls}.{fn.name}" if cls else fn.name)
        end = fn.end_lineno or fn.lineno
        functions[fid] = FuncNode(
            id=fid, name=fn.name, kind="method" if cls else "function", cls=cls,
            lineno=fn.lineno, source="\n".join(lines[fn.lineno - 1:end]),
            signature=f"({ast.unparse(fn.args)})", file=path.name,
        )
        node_id[id(fn)] = fid
        parent_of[fid] = parent
        ast_of[fid] = fn
        if parent:
            nested.setdefault(parent, {})[fn.name] = fid
        return fid

    def visit(body: list[ast.stmt], parent: str | None) -> None:
        for node in body:
            if isinstance(node, _FUNC):
                visit(node.body, register(node, None, parent))
            elif isinstance(node, ast.ClassDef) and parent is None:
                class_names.add(node.name)
                group = ClassGroup(name=node.name, lineno=node.lineno, file=path.name)
                for sub in node.body:
                    if isinstance(sub, _FUNC):
                        fid = register(sub, node.name, None)
                        group.members.append(fid)
                        visit(sub.body, fid)
                classes.append(group)

    visit(tree.body, None)

    # --- contexte du module : imports, globales ---------------------------- #
    imports: set[str] = set()
    import_map: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                alias = (a.asname or a.name).split(".")[0]
                imports.add(alias)
                import_map[alias] = a.name
        elif isinstance(node, ast.ImportFrom):
            mod = "." * (node.level or 0) + (node.module or "")
            for a in node.names:
                alias = a.asname or a.name
                imports.add(alias)
                import_map[alias] = f"{mod}.{a.name}" if mod else a.name

    globals_: set[str] = set()
    for node in tree.body:                        # noms définis au niveau module
        if isinstance(node, ast.Assign):
            for t in node.targets:
                globals_.update(n.id for n in ast.walk(t) if isinstance(n, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            globals_.add(node.target.id)

    # --- types d'attributs : self.x = Classe(...) --------------------------- #
    attr_types: dict[str, dict[str, str]] = {c.name: {} for c in classes}
    for cls_node in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        for sub in ast.walk(cls_node):
            if not (isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call)):
                continue
            ctor = _call_target(sub.value)
            if not (ctor and len(ctor) == 1 and ctor[0] in class_names):
                continue
            for tgt in sub.targets:
                if (isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name)
                        and tgt.value.id == "self"):
                    attr_types[cls_node.name][tgt.attr] = ctor[0]

    # --- passe 2 : résoudre les appels -------------------------------------- #
    edges: list[Edge] = []
    externals: dict[str, ExternalNode] = {}

    _scope_cache: dict[str, tuple[set[str], dict[str, str]]] = {}

    def scope_of(fid: str) -> tuple[set[str], dict[str, str]]:
        """Noms liés et fonctions imbriquées visibles depuis `fid`,
        en remontant la chaîne des fonctions englobantes (fermetures)."""
        if fid in _scope_cache:
            return _scope_cache[fid]
        names = _bound_names(ast_of[fid])
        inner = dict(nested.get(fid, {}))
        parent = parent_of.get(fid)
        if parent:
            pnames, pinner = scope_of(parent)
            names |= pnames
            inner = {**pinner, **inner}           # les sœurs restent visibles
        _scope_cache[fid] = (names, inner)
        return _scope_cache[fid]

    def method_of(cname: str | None, mname: str) -> str | None:
        cand = f"{cname}.{mname}"
        return cand if cname and cand in functions else None

    def add_external(target: tuple[str, ...], src: str, kind: str, line: int) -> None:
        head, *rest = target
        if kind == "builtin":
            head, rest = "builtins", list(target)
        elif kind == "unknown":
            head, rest = "?", list(target)
        ext = externals.setdefault(head, ExternalNode(id=f"ext:{head}", name=head,
                                                      kind=kind))
        member = ".".join(rest)
        if member and member not in ext.members:
            ext.members.append(member)
        edges.append(Edge(src=src, dst=ext.id, lineno=line, external=True,
                          symbol=".".join(target)))

    for fn_node in ast.walk(tree):
        if not isinstance(fn_node, _FUNC):
            continue
        src_id = node_id.get(id(fn_node))
        if src_id is None:
            continue
        cls = functions[src_id].cls
        local, inner = scope_of(src_id)

        local_types: dict[str, str] = {}          # var = ClasseLocale(...)
        imported_types: dict[str, str] = {}       # var = ClasseImportée(...)
        for sub in ast.walk(fn_node):
            if not (isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call)):
                continue
            ctor = _call_target(sub.value)
            if not (ctor and len(ctor) == 1):
                continue
            names = [t.id for t in sub.targets if isinstance(t, ast.Name)]
            if ctor[0] in class_names:
                local_types.update(dict.fromkeys(names, ctor[0]))
            elif ctor[0] in imports:
                imported_types.update(dict.fromkeys(names, ctor[0]))

        collector = _CallCollector()
        collector.visit(fn_node)
        seen: set[tuple[str, int]] = set()

        for target, line in collector.calls:
            head, *rest = target
            resolved: str | None = None
            skip = False

            if head in ("self", "cls") and cls:
                if len(rest) == 1:
                    resolved = method_of(cls, rest[0])
                elif len(rest) == 2:
                    resolved = method_of(attr_types.get(cls, {}).get(rest[0]), rest[1])
            elif not rest:
                if head in inner:                          # fonction imbriquée
                    resolved = inner[head]
                elif head in functions and head not in local:
                    resolved = head
                elif head in class_names:
                    resolved = method_of(head, "__init__")
                    skip = resolved is None                # classe sans __init__
            elif head in class_names:
                resolved = method_of(head, rest[0])
            elif head in local_types:
                resolved = method_of(local_types[head], rest[0])

            if skip:
                continue
            key = (resolved or ".".join(target), line)
            if key in seen:
                continue
            seen.add(key)

            if resolved:
                edges.append(Edge(src=src_id, dst=resolved, lineno=line))
            elif head in imported_types and rest:
                # obj.methode() sur une classe importée : reliable entre fichiers
                add_external((imported_types[head], *rest), src_id, "module", line)
            elif head in imports:
                add_external(target, src_id, "module", line)
            elif head in _BUILTINS:
                add_external(target, src_id, "builtin", line)
            elif head in local or head in globals_ or head in ("self", "cls"):
                continue                                   # appel sur une donnée
            else:
                add_external(target, src_id, "unknown", line)

    return Graph(
        path=str(path), functions=list(functions.values()),
        externals=list(externals.values()), classes=classes, edges=edges,
        lang="python", files=[path.name],
        meta={path.name: {"imports": import_map}},
    )
