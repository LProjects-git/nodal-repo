"""nodal.cpp — analyse d'un fichier C/C++.

Deux backends, sélectionnés automatiquement :

* **scanner** (défaut, zéro dépendance) : neutralise commentaires et littéraux,
  puis suit les accolades pour délimiter portées et corps de fonctions. Robuste
  sur du code courant, approximatif sur la métaprogrammation lourde.
* **libclang** (si `pip install libclang` aboutit) : véritable AST, exact sur
  les templates, les surcharges et les définitions hors-ligne.

Les deux produisent le même `Graph` que le frontend Python.
"""

from __future__ import annotations

import re
from pathlib import Path

from .model import AnalysisError, ClassGroup, Edge, ExternalNode, FuncNode, Graph

# Mots-clés suivis d'une parenthèse qui ne sont *pas* des appels.
_NOT_CALLS = {
    "if", "else", "for", "while", "switch", "catch", "return", "sizeof",
    "alignof", "typeid", "decltype", "static_assert", "noexcept", "throw",
    "case", "do", "new", "delete", "and", "or", "not", "defined", "assert",
    "static_cast", "dynamic_cast", "const_cast", "reinterpret_cast",
}
# Spécificateurs qui ne peuvent pas être un nom de fonction.
_SPECIFIERS = {
    "inline", "static", "virtual", "explicit", "constexpr", "consteval",
    "friend", "extern", "template", "typename", "class", "struct", "enum",
    "public", "private", "protected", "const", "volatile", "mutable",
    "unsigned", "signed", "auto", "operator", "using", "namespace", "typedef",
    "co_return", "co_await", "co_yield", "requires", "void", "int", "char",
    "bool", "float", "double", "long", "short", "size_t", "nullptr",
}

_ID = r"[A-Za-z_~][A-Za-z_0-9]*"


# --------------------------------------------------------------------------- #
# Nettoyage : neutralise commentaires et littéraux en préservant les positions
# --------------------------------------------------------------------------- #

def _blank(text: str) -> str:
    """Remplace commentaires, chaînes et caractères par des espaces.

    Lignes et colonnes sont préservées : une position trouvée dans le texte
    nettoyé reste valide dans l'original.
    """
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c, two = text[i], text[i:i + 2]
        if c == "#" and (i == 0 or text.rfind("\n", 0, i) == i - 1
                         or text[text.rfind("\n", 0, i) + 1:i].strip() == ""):
            j = i                                        # directive : ligne(s) entière(s)
            while True:
                nl = text.find("\n", j)
                if nl < 0:
                    j = n; break
                if text[max(i, nl - 1):nl].rstrip().endswith("\\"):
                    j = nl + 1; continue                 # continuation de ligne
                j = nl; break
            out.append("".join(ch if ch == "\n" else " " for ch in text[i:j])); i = j
        elif two == "//":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif two == "/*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join(ch if ch == "\n" else " " for ch in text[i:j])); i = j
        elif c in "\"'":
            j, quote = i + 1, c
            while j < n and text[j] != quote:
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            out.append("".join(ch if ch == "\n" else " " for ch in text[i:j])); i = j
        else:
            out.append(c); i += 1
    return "".join(out)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _match(text: str, pos: int, opener: str, closer: str) -> int:
    """Position du délimiteur fermant correspondant à `text[pos] == opener`."""
    depth = 0
    for i in range(pos, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return i
    return -1


def _body_brace(text: str, close_paren: int) -> int:
    """Position du '{' du corps après ')', en sautant `const`, `noexcept`,
    `override` et une éventuelle liste d'initialisation `: a(1), b(2)`.
    Retourne -1 s'il s'agit d'une déclaration (`;`) et non d'une définition.
    """
    i, n = close_paren + 1, len(text)
    while i < n:
        c = text[i]
        if c == "{":
            return i
        if c in ";}=":
            return -1
        if c == "(":                                    # membre de liste d'init
            j = _match(text, i, "(", ")")
            if j < 0:
                return -1
            i = j + 1
            continue
        i += 1
    return -1


# --------------------------------------------------------------------------- #
# Backend scanner (sans dépendance)
# --------------------------------------------------------------------------- #

_SCOPE_RE = re.compile(
    rf"\b(?P<kw>class|struct|namespace)\s+(?P<name>{_ID})"
    rf"(?P<tail>[^;{{}}()]*?)(?P<brace>\{{)")

_FUNC_RE = re.compile(
    rf"(?P<qual>(?:{_ID}\s*::\s*)*)"                    # Foo:: (hors-ligne)
    rf"(?P<name>~?{_ID}|operator\s*\S{{1,2}})\s*(?P<paren>\()")

_CALL_RE = re.compile(
    rf"(?:(?P<recv>{_ID})\s*(?P<op>\.|->|::)\s*)?(?P<name>~?{_ID})\s*\(")


def _scan(path: Path, text: str) -> Graph:
    clean = _blank(text)
    lines = text.splitlines()

    # --- portées : classes, structs, namespaces ---------------------------- #
    scopes: list[tuple[int, int, str, str]] = []       # (début, fin, nom, mot-clé)
    bases: dict[str, list[str]] = {}                   # classe -> classes de base
    for m in _SCOPE_RE.finditer(clean):
        b = m.start("brace")
        end = _match(clean, b, "{", "}")
        if end < 0:
            continue
        scopes.append((b, end, m.group("name"), m.group("kw")))
        tail = m.group("tail")
        if ":" in tail:
            bases[m.group("name")] = [
                x for x in re.findall(_ID, tail.split(":", 1)[1])
                if x not in _SPECIFIERS
            ]

    def scope_of(pos: int) -> tuple[str | None, str]:
        """Nom et type de la portée la plus imbriquée contenant `pos`."""
        best, kind, span = None, "class", len(clean) + 1
        for s, e, name, kw in scopes:
            if s < pos < e and (e - s) < span:
                best, kind, span = name, kw, e - s
        return best, kind

    # --- définitions de fonctions ------------------------------------------ #
    functions: dict[str, FuncNode] = {}
    bodies: list[tuple[str, int, int, str | None]] = []   # (id, début, fin, classe)

    for m in _FUNC_RE.finditer(clean):
        name = re.sub(r"\s+", "", m.group("name"))
        if name in _NOT_CALLS or name in _SPECIFIERS:
            continue
        close = _match(clean, m.start("paren"), "(", ")")
        if close < 0:
            continue
        brace = _body_brace(clean, close)
        if brace < 0:
            continue                                    # déclaration, pas définition

        before = clean[max(0, m.start() - 120):m.start()]
        prev = re.search(r"(\S+)\s*$", before)
        prev_tok = prev.group(1) if prev else ""
        if prev_tok in (":", ","):
            continue                                    # membre de liste d'init
        if prev_tok and prev_tok[-1] in "=+-*/%!&|,([":
            continue                                    # expression, pas définition
        if prev_tok.endswith(">") and "<" not in before[-120:]:
            continue                                    # comparaison, pas template

        qual = re.sub(r"\s+", "", m.group("qual")).rstrip(":")
        if not qual and not prev_tok:
            continue                                    # pas de type de retour

        outer = qual.split("::")[-1] if qual else None
        cls, kw = (outer, "class") if outer else scope_of(m.start())
        if kw == "namespace" and not outer:
            cls = None                                  # fonction libre de namespace

        fid = f"{cls}.{name}" if cls else name
        if fid in functions:                            # surcharge : identifiant unique
            fid = f"{fid}#{sum(1 for k in functions if k.split('#')[0] == fid)}"

        end = _match(clean, brace, "{", "}")
        l0, l1 = _line_of(text, m.start()), _line_of(text, end)
        functions[fid] = FuncNode(
            id=fid, name=name, kind="method" if cls else "function", cls=cls,
            lineno=l0, source="\n".join(lines[l0 - 1:l1]),
            signature=re.sub(r"\s+", " ", clean[m.start("paren"):close + 1]).strip(),
            file=path.name,
        )
        bodies.append((fid, brace, end, cls))

    # --- groupes : classes/structs puis namespaces -------------------------- #
    namespaces = {name for _, _, name, kw in scopes if kw == "namespace"}
    classes: dict[str, ClassGroup] = {}
    for s, _e, name, kw in scopes:
        if kw != "namespace" and any(f.cls == name for f in functions.values()):
            classes[name] = ClassGroup(name=name, lineno=_line_of(text, s),
                                       stereotype=kw)
    for f in functions.values():                        # classes définies ailleurs
        if f.cls and f.cls not in classes:
            classes[f.cls] = ClassGroup(name=f.cls, lineno=f.lineno)
    for f in functions.values():
        if f.cls:
            classes[f.cls].members.append(f.id)
    for s, e, name, kw in scopes:
        if kw != "namespace":
            continue
        inner = [fid for fid, b, _, c in bodies if c is None and s < b < e]
        if inner:
            classes[name] = ClassGroup(name=name, lineno=_line_of(text, s),
                                       members=inner, stereotype="namespace")

    # --- attributs membres typés par une classe connue : `Store store_;` ---- #
    fn_spans = [(b, e) for _, b, e, _ in bodies]
    attr_by_class: dict[str, dict[str, str]] = {}
    for s, e, cname, kw in scopes:
        if kw == "namespace":
            continue
        decls = {}
        for m in re.finditer(rf"\b({_ID})\s*[*&]?\s+({_ID})\s*[;={{]", clean[s:e]):
            pos = s + m.start()
            if any(fs < pos < fe for fs, fe in fn_spans):
                continue                                # dans un corps de fonction
            if m.group(1) in classes and m.group(1) not in _SPECIFIERS:
                decls[m.group(2)] = m.group(1)
        if decls:
            attr_by_class[cname] = decls

    # --- appels ------------------------------------------------------------- #
    by_name: dict[str, list[str]] = {}
    for f in functions.values():
        by_name.setdefault(f.name, []).append(f.id)

    def arity(sig: str) -> int:
        """Nombre de paramètres d'une signature `(a, b)` (virgules de niveau 0)."""
        inner = sig[1:-1].strip()
        if not inner:
            return 0
        depth, count = 0, 1
        for ch in inner:
            depth += (ch in "(<[") - (ch in ")>]")
            count += (ch == "," and depth == 0)
        return count

    def pick(cands: list[str], nargs: int | None) -> str | None:
        """Parmi des surcharges, celle dont l'arité correspond à l'appel."""
        if not cands:
            return None
        if nargs is None or len(cands) == 1:
            return cands[0]
        return next((c for c in cands if arity(functions[c].signature) == nargs),
                    cands[0])

    edges: list[Edge] = []
    externals: dict[str, ExternalNode] = {}
    includes = [m.group(1) for m in
                re.finditer(r"#\s*include\s*[<\"]([^>\"]+)[>\"]", text)]

    def add_external(group: str, member: str, src: str, line: int,
                     kind: str = "module") -> None:
        ext = externals.setdefault(group, ExternalNode(id=f"ext:{group}", name=group,
                                                       kind=kind))
        if member and member not in ext.members:
            ext.members.append(member)
        symbol = f"{group}::{member}" if kind in ("module", "deferred") else member
        edges.append(Edge(src=src, dst=ext.id, lineno=line, external=True,
                          symbol=symbol))

    def method_of(cname: str | None, mname: str, nargs: int | None = None,
                  seen_cls: frozenset[str] = frozenset()) -> str | None:
        """Cherche `mname` dans `cname`, puis dans ses classes de base."""
        if not cname or cname in seen_cls:
            return None
        hit = pick([i for i in by_name.get(mname, [])
                    if functions[i].cls == cname], nargs)
        if hit:
            return hit
        for base in bases.get(cname, []):              # héritage
            hit = method_of(base, mname, nargs, seen_cls | {cname})
            if hit:
                return hit
        return None

    for fid, start, end, cls in bodies:
        body = clean[start:end]
        # types locaux : `Foo bar;`, `Foo bar(...)`, `x = new Foo(`
        local: dict[str, str] = dict(attr_by_class.get(cls or "", {}))
        declared: dict[str, str] = {}          # var -> type, y compris types inconnus
        for m in re.finditer(
                rf"\b({_ID})\s*(?:<[^<>;{{}}]*>)?\s*[*&]?\s+({_ID})\s*[;=({{]", body):
            if m.group(1) in _SPECIFIERS:
                continue
            if m.group(1) in classes:
                local[m.group(2)] = m.group(1)
            else:
                declared[m.group(2)] = m.group(1)
        for m in re.finditer(rf"\b({_ID})\s*=\s*(?:new\s+)?({_ID})\s*[({{]", body):
            if m.group(2) in classes:
                local[m.group(1)] = m.group(2)

        seen: set[tuple[str, int]] = set()
        for m in _CALL_RE.finditer(body):
            name, recv, op = m.group("name"), m.group("recv"), m.group("op")
            if name in _NOT_CALLS or name in _SPECIFIERS or recv in _NOT_CALLS:
                continue
            line = _line_of(text, start + m.start("name"))
            close_c = _match(body, m.end() - 1, "(", ")")
            nargs = arity(body[m.end() - 1:close_c + 1]) if close_c > 0 else None

            # `Type var(...)` : déclaration — la cible est le constructeur du type.
            if recv is None and name not in by_name:
                pre = body[max(0, m.start() - 80):m.start()]
                tok = re.search(rf"({_ID})\s*(?:<[^<>;{{}}]*>)?\s*[*&]?\s*$", pre)
                tname = tok.group(1) if tok else None
                if tname and tname not in _SPECIFIERS and tname not in _NOT_CALLS:
                    ctor = method_of(tname, tname)
                    if ctor:
                        edges.append(Edge(src=fid, dst=ctor, lineno=line))
                    else:                               # défini ailleurs ? à relier
                        add_external(tname, tname, fid, line, kind="deferred")
                    continue

            target: str | None = None
            if recv is None:
                target = method_of(cls, name, nargs) or \
                    pick([i for i in by_name.get(name, [])], nargs)
            elif recv == "this":
                target = method_of(cls, name, nargs)
            elif recv in local:                         # obj.methode() / ptr->m()
                target = method_of(local[recv], name, nargs)
            elif recv in namespaces:                    # ns::fonction()
                target = pick([i for i in by_name.get(name, [])
                               if functions[i].cls is None], nargs)
            elif recv in classes:                       # Classe::methode()
                target = method_of(recv, name, nargs)

            key = (target or f"{recv}::{name}", line)
            if key in seen:
                continue
            seen.add(key)

            if target:
                edges.append(Edge(src=fid, dst=target, lineno=line))
            elif recv and op == "::":                   # std::sort, ns::f
                add_external(recv, name, fid, line)
            elif recv in declared:                      # obj.m() sur un type inconnu
                add_external(declared[recv], name, fid, line, kind="deferred")
            elif recv:
                continue                                # méthode d'un type externe
            elif name not in classes:
                add_external("?", name, fid, line, kind="unknown")

    for c in classes.values():
        c.file = path.name
    return Graph(path=str(path), functions=list(functions.values()),
                 externals=list(externals.values()), classes=list(classes.values()),
                 edges=edges, lang="cpp", files=[path.name],
                 meta={path.name: {"includes": includes}})


# --------------------------------------------------------------------------- #
# Backend libclang (optionnel, plus précis)
# --------------------------------------------------------------------------- #

def _clang(path: Path, text: str, args: list[str]) -> Graph:
    from clang.cindex import CursorKind, Index, TranslationUnit

    tu = Index.create().parse(
        str(path), args=args or ["-std=c++17"],
        options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
        | TranslationUnit.PARSE_INCOMPLETE,
    )
    lines = text.splitlines()
    defs = {CursorKind.FUNCTION_DECL, CursorKind.CXX_METHOD,
            CursorKind.CONSTRUCTOR, CursorKind.DESTRUCTOR,
            CursorKind.FUNCTION_TEMPLATE}
    holders = {CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL,
               CursorKind.CLASS_TEMPLATE}

    functions: dict[str, FuncNode] = {}
    classes: dict[str, ClassGroup] = {}
    externals: dict[str, ExternalNode] = {}
    edges: list[Edge] = []

    def in_file(c) -> bool:
        return bool(c.location.file and Path(c.location.file.name).name == path.name)

    def node_id(c) -> str:
        p = c.semantic_parent
        return f"{p.spelling}.{c.spelling}" if p and p.kind in holders else c.spelling

    for c in tu.cursor.walk_preorder():
        if c.kind not in defs or not in_file(c) or not c.is_definition():
            continue
        fid = node_id(c)
        if fid in functions:
            fid = f"{fid}#{len(functions)}"
        l0, l1 = c.extent.start.line, c.extent.end.line
        p = c.semantic_parent
        cls = p.spelling if p and p.kind in holders else None
        functions[fid] = FuncNode(
            id=fid, name=c.spelling, kind="method" if cls else "function", cls=cls,
            lineno=l0, source="\n".join(lines[l0 - 1:l1]),
            signature="(" + ", ".join(a.type.spelling for a in c.get_arguments()) + ")",
            file=path.name)
        if cls:
            classes.setdefault(cls, ClassGroup(
                name=cls, lineno=p.location.line,
                stereotype="struct" if p.kind == CursorKind.STRUCT_DECL else "class",
            )).members.append(fid)

    by_line = {(f.lineno, f.name): f.id for f in functions.values()}
    by_name: dict[str, str] = {}
    for f in functions.values():
        by_name.setdefault(f.name, f.id)

    def add_ext(group: str, member: str, src: str, line: int) -> None:
        kind = "unknown" if group == "external" else "module"
        ext = externals.setdefault(group, ExternalNode(id=f"ext:{group}", name=group,
                                                       kind=kind))
        if member and member not in ext.members:
            ext.members.append(member)
        edges.append(Edge(src=src, dst=ext.id, lineno=line, external=True,
                          symbol=member))

    for c in tu.cursor.walk_preorder():
        if c.kind not in defs or not in_file(c) or not c.is_definition():
            continue
        src = by_line.get((c.extent.start.line, c.spelling))
        if src is None:
            continue
        seen: set[tuple[str, int]] = set()
        for sub in c.walk_preorder():
            if sub.kind != CursorKind.CALL_EXPR:
                continue
            ref = sub.referenced
            if ref is None or not ref.spelling:
                continue
            line, target = sub.location.line, None
            if in_file(ref):
                target = by_line.get((ref.extent.start.line, ref.spelling)) \
                    or by_name.get(ref.spelling)
            key = (target or ref.spelling, line)
            if key in seen:
                continue
            seen.add(key)
            if target and target != src:
                edges.append(Edge(src=src, dst=target, lineno=line))
            elif not target:
                ns = ref.semantic_parent
                group = ns.spelling if ns and ns.kind == CursorKind.NAMESPACE else ""
                add_ext(group or "external", ref.spelling, src, line)

    for c in classes.values():
        c.file = path.name
    return Graph(path=str(path), functions=list(functions.values()),
                 externals=list(externals.values()), classes=list(classes.values()),
                 edges=edges, lang="cpp", files=[path.name])


# --------------------------------------------------------------------------- #
# Entrée publique
# --------------------------------------------------------------------------- #

def analyze_cpp(path: str | Path, *, backend: str = "scanner",
                clang_args: list[str] | None = None) -> Graph:
    """Analyse un fichier C/C++ (`.cpp`, `.cc`, `.hpp`, `.h`...).

    `backend` : "scanner" (défaut, sans dépendance), "clang" (exige libclang)
    ou "auto" (libclang si disponible, sinon scanner).
    `clang_args` : options de compilation, ex. ["-std=c++20", "-Iinclude"].
    """
    path = Path(path)
    if not path.is_file():
        raise AnalysisError(f"Fichier introuvable : {path}")
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise AnalysisError(f"Lecture impossible : {exc}") from exc

    if backend in ("auto", "clang"):
        try:
            return _clang(path, text, clang_args or [])
        except Exception as exc:
            if backend == "clang":
                raise AnalysisError(
                    f"Backend libclang indisponible ({exc}). "
                    f"Essayez `pip install libclang` ou backend='scanner'."
                ) from exc
    return _scan(path, text)
