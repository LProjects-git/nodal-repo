"""nodal.analyzer — analyse statique d'un fichier Python.

Extrait fonctions, méthodes et classes via l'AST, puis construit le
graphe d'appels : qui appelle qui, à quelle ligne, et quels appels
sortent vers l'extérieur (modules importés, builtins...).
"""

from __future__ import annotations

import ast
from pathlib import Path

from .model import AnalysisError, ClassGroup, Edge, ExternalNode, FuncNode, Graph


# --------------------------------------------------------------------------- #
# Extraction des appels au sein d'une fonction
# --------------------------------------------------------------------------- #

def _call_target(node: ast.Call) -> tuple[str, ...] | None:
    """Retourne la chaîne d'attributs d'un appel : foo() -> ("foo",),
    self.bar() -> ("self","bar"), os.path.join() -> ("os","path","join")."""
    parts: list[str] = []
    cur: ast.expr = node.func
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return tuple(reversed(parts))
    return None  # appel dynamique : (f())(), lambda, indexation...


class _CallCollector(ast.NodeVisitor):
    """Collecte les appels d'une fonction sans descendre dans ses defs imbriqués."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], int]] = []
        self._depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._depth == 0:            # la fonction analysée elle-même
            self._depth += 1
            self.generic_visit(node)
            self._depth -= 1
        # sinon : fonction imbriquée, on n'y entre pas (appels comptés à part)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        target = _call_target(node)
        if target:
            self.calls.append((target, node.lineno))
        self.generic_visit(node)


# --------------------------------------------------------------------------- #
# Analyse du module
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

    def register(fn: ast.FunctionDef | ast.AsyncFunctionDef, cls: str | None) -> None:
        fid = f"{cls}.{fn.name}" if cls else fn.name
        end = fn.end_lineno or fn.lineno
        functions[fid] = FuncNode(
            id=fid,
            name=fn.name,
            kind="method" if cls else "function",
            cls=cls,
            lineno=fn.lineno,
            source="\n".join(lines[fn.lineno - 1 : end]),
            signature=f"({ast.unparse(fn.args)})",
        )

    # Passe 1 : recenser toutes les définitions (top-level uniquement).
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            register(node, None)
        elif isinstance(node, ast.ClassDef):
            group = ClassGroup(name=node.name, lineno=node.lineno)
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    register(sub, node.name)
                    group.members.append(f"{node.name}.{sub.name}")
            classes.append(group)

    class_names = {c.name for c in classes}

    # Passe 2 : résoudre les appels de chaque fonction.
    import builtins as _bi
    builtin_names = set(dir(_bi))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imports |= {a.asname or a.name for a in node.names}

    # Types des attributs d'instance : self.x = Classe(...) -> {Classe: {x: Classe}}
    attr_types: dict[str, dict[str, str]] = {c.name: {} for c in classes}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            ctor = _call_target(node.value)
            if not (ctor and len(ctor) == 1 and ctor[0] in class_names):
                continue
            for tgt in node.targets:
                if (isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name)
                        and tgt.value.id == "self"):
                    for c in classes:                   # classe englobante ?
                        span = [functions[m].lineno for m in c.members]
                        if span and min(span) <= node.lineno:
                            attr_types[c.name][tgt.attr] = ctor[0]

    edges: list[Edge] = []
    externals: dict[str, ExternalNode] = {}

    def method_of(cname: str, mname: str) -> str | None:
        cand = f"{cname}.{mname}"
        return cand if cand in functions else None

    def resolve(target: tuple[str, ...], cls: str | None,
                local_types: dict[str, str]) -> str | None:
        """Renvoie l'id du nœud interne appelé, sinon None (externe/inconnu)."""
        head, *rest = target
        if head in ("self", "cls") and cls:
            if len(rest) == 1:                          # self.methode()
                return method_of(cls, rest[0])
            if len(rest) == 2:                          # self.attr.methode()
                atype = attr_types.get(cls, {}).get(rest[0])
                return method_of(atype, rest[1]) if atype else None
            return None
        if not rest:
            if head in functions:                       # fonction du module
                return head
            if head in class_names:                     # instanciation Classe()
                return f"{head}.__init__" if f"{head}.__init__" in functions                     else f"class:{head}"
            return None
        if head in class_names:                         # Classe.methode(...)
            return method_of(head, rest[0])
        if head in local_types:                         # var = Classe(); var.m()
            return method_of(local_types[head], rest[0])
        return None

    def add_external(target: tuple[str, ...], src: str, lineno: int,
                     local_names: set[str]) -> None:
        head, *rest = target
        if head in builtin_names and head not in imports:
            head, rest = "builtins", list(target)       # regrouper les builtins
        elif head in local_names or head in ("self", "cls"):
            return                                      # variable locale : bruit
        ext = externals.setdefault(head, ExternalNode(id=f"ext:{head}", name=head))
        member = ".".join(rest)
        if member and member not in ext.members:
            ext.members.append(member)
        edges.append(Edge(src=src, dst=ext.id, lineno=lineno, external=True))

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        cls = next((c.name for c in classes
                    if f"{c.name}.{node.name}" in c.members), None)
        src_id = f"{cls}.{node.name}" if cls else node.name
        if src_id not in functions or functions[src_id].lineno != node.lineno:
            continue  # def imbriqué ou homonyme : ignoré

        # Noms locaux + inférence : var = Classe(...) dans le corps.
        local_names = {a.arg for a in ast.walk(node.args) if isinstance(a, ast.arg)}
        local_types: dict[str, str] = {}
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign):
                names = [t.id for t in sub.targets if isinstance(t, ast.Name)]
                local_names |= set(names)
                if isinstance(sub.value, ast.Call):
                    ctor = _call_target(sub.value)
                    if ctor and len(ctor) == 1 and ctor[0] in class_names:
                        local_types.update(dict.fromkeys(names, ctor[0]))

        collector = _CallCollector()
        collector.visit(node)
        seen: set[tuple[str, int]] = set()
        for target, lineno in collector.calls:
            resolved = resolve(target, cls, local_types)
            if resolved and resolved.startswith("class:"):
                continue                                # classe sans __init__
            key = (resolved or target[0], lineno)
            if key in seen:
                continue
            seen.add(key)
            if resolved:
                edges.append(Edge(src=src_id, dst=resolved, lineno=lineno))
            else:
                add_external(target, src_id, lineno, local_names)

    return Graph(
        path=str(path),
        functions=list(functions.values()),
        externals=list(externals.values()),
        classes=classes,
        edges=edges,
        lang="python",
    )
