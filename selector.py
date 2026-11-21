"""RWX Blast Radius selector, v2.

For every patch in /data/commits, print one JSON line {"commit", "workers"}.

Evidence comes only from an index built offline from the *pinned, unmodified*
sqlglot checkout (see tools/): per-test line coverage with import/collection
contexts separated, files each test read, and sqlglot classes each test
instantiated.  The selector never sees sample answers, and contains no table
keyed by patch, commit id or edit kind.

Selection rule, per changed unit (decided by AST comparison, not by text):
  * AST-identical file (comments/whitespace only)  -> no tests from that file
  * statement inside a function/lambda changed     -> tests that executed that
    statement in the pinned run (a test that never executes a statement
    cannot observe a change to it)
  * import-time statement (module or class body)   -> tests that use the
    module/class (instantiated it or a subclass, ran its code, or a module
    that imports it)
  * data file (fixtures etc.)                      -> tests that read it
Anything that cannot be analysed falls back to a broad, safe selection.
stdout carries only the JSON lines; diagnostics go to stderr.
"""

from __future__ import annotations

import ast
import difflib
import gzip
import json
import os
import re
import sys
from pathlib import Path

DATA = Path(os.environ.get("RWX_DATA", "/data"))
HERE = Path(__file__).resolve().parent
INDEX_DIR = Path(os.environ.get("RWX_INDEX", HERE / "index"))
MAX_WORKERS = 8
WORKER_COST_MS = 2000
DEBUG = os.environ.get("RWX_DEBUG") == "1"


def log(*a):
    if DEBUG:
        print(*a, file=sys.stderr)


# ===================================================================== patches
class FileDiff:
    __slots__ = ("old", "new", "hunks", "binary")

    def __init__(self):
        self.old = None
        self.new = None
        self.hunks = []  # (old_start, old_len, new_start, new_len, [lines])
        self.binary = False

    @property
    def path(self):
        return self.old if self.old is not None else self.new


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _clean_path(p: str) -> str | None:
    p = p.rstrip("\r\n")
    if "\t" in p:
        p = p.split("\t", 1)[0]
    if p.startswith('"') and p.endswith('"') and len(p) >= 2:
        try:
            p = p[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape").encode("latin-1").decode("utf-8")
        except Exception:
            p = p[1:-1]
    if p == "/dev/null":
        return None
    if p[:2] in ("a/", "b/"):
        p = p[2:]
    return p


def parse_patch(text: str) -> list[FileDiff]:
    """Parse a git unified diff. Raises ValueError when nothing is recognisable."""
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    hunk = None
    lines = text.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip("\r")
        if line.startswith("diff --git "):
            cur = FileDiff()
            files.append(cur)
            hunk = None
            m = re.match(r'^diff --git (?:"?a/(.+?)"?) (?:"?b/(.+?)"?)$', line)
            if m:
                cur.old, cur.new = m.group(1), m.group(2)
        elif cur is not None and hunk is None and line.startswith("--- "):
            cur.old = _clean_path(line[4:])
        elif cur is not None and hunk is None and line.startswith("+++ "):
            cur.new = _clean_path(line[4:])
        elif cur is not None and line.startswith("new file mode"):
            cur.old = None
        elif cur is not None and line.startswith("deleted file mode"):
            cur.new = None
        elif cur is not None and line.startswith("rename from "):
            cur.old = line[12:]
        elif cur is not None and line.startswith("rename to "):
            cur.new = line[10:]
        elif cur is not None and (line.startswith("Binary files") or line.startswith("GIT binary patch")):
            cur.binary = True
        elif cur is not None and line.startswith("@@"):
            m = _HUNK.match(line)
            if not m:
                raise ValueError("bad hunk header")
            os_, ol, ns, nl = m.groups()
            ol = 1 if ol is None else int(ol)
            nl = 1 if nl is None else int(nl)
            hunk = (int(os_), ol, int(ns), nl, [])
            cur.hunks.append(hunk)
            # consume exactly the declared number of lines
            need_old, need_new = ol, nl
            i += 1
            while i < n and (need_old > 0 or need_new > 0):
                hl = lines[i]
                tag = hl[:1]
                if tag == " " or (hl == "" and need_old > 0 and need_new > 0):
                    hunk[4].append(" " + hl[1:])
                    need_old -= 1
                    need_new -= 1
                elif tag == "-":
                    hunk[4].append(hl)
                    need_old -= 1
                elif tag == "+":
                    hunk[4].append(hl)
                    need_new -= 1
                elif tag == "\\":
                    pass
                else:
                    raise ValueError("truncated hunk")
                i += 1
            while i < n and lines[i].startswith("\\"):
                hunk[4].append(lines[i])
                i += 1
            continue
        i += 1
    if not files:
        raise ValueError("no files in patch")
    return files


def apply_hunks(base: str, hunks) -> str:
    """Apply hunks to base text; raise ValueError on context mismatch."""
    src = base.split("\n")
    out: list[str] = []
    pos = 0  # 0-based index into src
    for old_start, old_len, _ns, _nl, body in hunks:
        start = old_start - 1 if old_len > 0 else old_start
        if start < pos or start > len(src):
            raise ValueError("hunk out of range")
        out.extend(src[pos:start])
        pos = start
        no_newline_after_new = False
        for idx, hl in enumerate(body):
            tag = hl[:1]
            if tag == "\\":
                prev = body[idx - 1][:1] if idx else ""
                if prev in ("+", " "):
                    no_newline_after_new = True
                continue
            if tag in (" ", "-"):
                if pos >= len(src) or src[pos].rstrip("\r") != hl[1:].rstrip("\r"):
                    raise ValueError("context mismatch")
                if tag == " ":
                    out.append(src[pos])
                pos += 1
            elif tag == "+":
                out.append(hl[1:])
        del no_newline_after_new
    out.extend(src[pos:])
    return "\n".join(out)


# ===================================================================== AST diff
_COMPOUND_BODIES = ("body", "orelse", "finalbody", "handlers", "cases")


def _dump(node) -> str:
    return ast.dump(node, include_attributes=False)


def _header_dump(node) -> str:
    """Dump of a statement with nested statement bodies removed."""
    parts = [type(node).__name__]
    for f, v in ast.iter_fields(node):
        if f in _COMPOUND_BODIES:
            continue
        if isinstance(v, list):
            parts.append(f + "=[" + ",".join(_dump(x) if isinstance(x, ast.AST) else repr(x) for x in v) + "]")
        elif isinstance(v, ast.AST):
            parts.append(f + "=" + _dump(v))
        else:
            parts.append(f + "=" + repr(v))
    return "|".join(parts)


def _shallow(node) -> str:
    """Statement dump where function and class bodies are opaque (they are
    separate units), so a change inside a method does not mark the class body."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return "DEF:" + _header_dump(node)
    return _dump(node)


def _header_end(node) -> int:
    """Last line of a compound statement's header."""
    first_body = None
    for f in _COMPOUND_BODIES:
        v = getattr(node, f, None)
        if v:
            ln = v[0].lineno if not isinstance(v[0], ast.match_case) else v[0].pattern.lineno
            if hasattr(v[0], "decorator_list") and v[0].decorator_list:
                ln = min(ln, v[0].decorator_list[0].lineno)
            first_body = ln if first_body is None else min(first_body, ln)
    if first_body is None:
        return getattr(node, "end_lineno", node.lineno)
    return max(node.lineno, first_body - 1)


def _start(node) -> int:
    ln = node.lineno
    for d in getattr(node, "decorator_list", ()) or ():
        ln = min(ln, d.lineno)
    return ln


class Units:
    """Split a module into units. scope units: module and class bodies
    (executed at import); function units: function bodies (executed when
    called)."""

    def __init__(self, tree: ast.Module):
        self.units: dict[str, tuple[str, list, ast.AST]] = {}
        self._walk(tree.body, "", "module", tree)

    def _add(self, qual, kind, body, node):
        k = qual
        j = 1
        while k in self.units:
            j += 1
            k = f"{qual}#{j}"
        self.units[k] = (kind, body, node)
        if body and isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            st = body[0]
            if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
                st._rwx_doc = True  # docstring (see _inert_string_stmt)
        return k

    def _walk(self, body, qual, kind, node):
        self._add(qual or "<module>", kind, body, node)
        self._children(body, qual, kind)

    def _children(self, body, qual, kind):
        for st in body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{qual}.{st.name}" if qual else st.name
                self._add(q, "function", st.body, st)
                self._children(st.body, q, "function")
            elif isinstance(st, ast.ClassDef):
                q = f"{qual}.{st.name}" if qual else st.name
                if kind == "function":
                    # classes created inside a function run when it runs
                    self._add(q, "function", st.body, st)
                else:
                    self._add(q, "class", st.body, st)
                self._children(st.body, q, "function" if kind == "function" else "class")
            else:
                for f in _COMPOUND_BODIES:
                    sub = getattr(st, f, None)
                    if sub:
                        stmts = [c for c in sub if isinstance(c, ast.stmt)]
                        if f == "handlers":
                            for h in sub:
                                self._children(h.body, qual, kind)
                        elif f == "cases":
                            for c in sub:
                                self._children(c.body, qual, kind)
                        else:
                            self._children(stmts, qual, kind)


class Change:
    __slots__ = ("kind", "unit", "lines", "detail", "lambdas", "node", "new_node")

    def __init__(self, kind, unit, lines, detail="", lambdas=None, node=None):
        self.node = node
        self.new_node = None
        self.kind = kind          # 'function' | 'class' | 'module' | 'defaults'
        self.unit = unit          # qualified unit name
        self.lines = lines        # list of (start, end) base line ranges
        self.detail = detail
        self.lambdas = lambdas    # for scope statements whose diff is inside lambdas

    def __repr__(self):
        return f"Change({self.kind},{self.unit},{self.lines},{self.detail})"


def _minimal_diffs(a, b, path=()):
    """Yield (node_in_a or None, path) for minimal differing subtrees."""
    if type(a) is not type(b):
        yield a, path
        return
    if isinstance(a, ast.AST):
        for f, va in ast.iter_fields(a):
            vb = getattr(b, f, None)
            yield from _minimal_diffs_field(va, vb, a, path + ((a, f),))
        return
    if a != b:
        yield None, path


def _minimal_diffs_field(va, vb, parent, path):
    if isinstance(va, list) and isinstance(vb, list):
        if len(va) != len(vb):
            yield parent, path
            return
        for x, y in zip(va, vb):
            if isinstance(x, ast.AST) or isinstance(y, ast.AST):
                if not (isinstance(x, ast.AST) and isinstance(y, ast.AST) and _dump(x) == _dump(y)):
                    yield from _minimal_diffs(x, y, path)
            elif x != y:
                yield parent, path
        return
    if isinstance(va, ast.AST) and isinstance(vb, ast.AST):
        if _dump(va) != _dump(vb):
            yield from _minimal_diffs(va, vb, path)
        return
    if va != vb:
        yield parent, path


def _lambda_only(a, b):
    """If every difference between statements a and b is inside lambda
    bodies, return those lambdas (from a); otherwise None."""
    lams = []
    for node, path in _minimal_diffs(a, b):
        lam = None
        for anc, field in path:
            if isinstance(anc, ast.Lambda) and field == "body":
                lam = anc
                break
        if lam is None:
            return None
        lams.append(lam)
    return lams or None


_ENUM_CLASSES = None
_ENUM_RE = re.compile(r"^\s*class\s+(\w+)\s*\(([^)]*)\)", re.M)


def enum_classes() -> set:
    global _ENUM_CLASSES
    if _ENUM_CLASSES is None:
        names = set()
        src = _SOURCES_FOR_ENUMS() or {}
        bases = {}
        for text in src.values():
            for m in _ENUM_RE.finditer(text):
                bases[m.group(1)] = [b.strip().split(".")[-1] for b in m.group(2).split(",")]
        roots = {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"}
        changed = True
        while changed:
            changed = False
            for c, bs in bases.items():
                if c not in names and any(b in roots or b in names for b in bs):
                    names.add(c)
                    changed = True
        _ENUM_CLASSES = names
    return _ENUM_CLASSES


_SOURCES_FOR_ENUMS = lambda: None  # set by Selector


def _is_singleton_operand(node) -> bool:
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    if isinstance(node, ast.Attribute):
        base = node.value
        name = base.id if isinstance(base, ast.Name) else base.attr if isinstance(base, ast.Attribute) else None
        return name is not None and name in enum_classes()
    return False


class _IsToEq(ast.NodeTransformer):
    """`x is None` == `x == None` and `x is E.M` == `x == E.M` for objects whose
    __eq__ is identity-like (None, Enum members)."""

    def visit_Compare(self, node):
        self.generic_visit(node)
        ops = []
        operands = [node.left] + list(node.comparators)
        for i, op in enumerate(node.ops):
            if isinstance(op, (ast.Is, ast.IsNot)) and (
                _is_singleton_operand(operands[i]) or _is_singleton_operand(operands[i + 1])
            ):
                op = ast.Eq() if isinstance(op, ast.Is) else ast.NotEq()
            ops.append(op)
        node.ops = ops
        return node


def _normalised(node) -> str:
    """_dump of `node` with _IsToEq applied, without copying the tree: the
    Compare ops are swapped in place and restored before returning."""
    saved = []
    try:
        for n in ast.walk(node):
            if isinstance(n, ast.Compare):
                operands = [n.left] + list(n.comparators)
                ops = []
                for i, op in enumerate(n.ops):
                    if isinstance(op, (ast.Is, ast.IsNot)) and (
                        _is_singleton_operand(operands[i]) or _is_singleton_operand(operands[i + 1])
                    ):
                        op = ast.Eq() if isinstance(op, ast.Is) else ast.NotEq()
                    ops.append(op)
                saved.append((n, n.ops))
                n.ops = ops
        return _dump(node)
    finally:
        for n, ops in saved:
            n.ops = ops


def _equivalent_stmt(a, b) -> bool:
    try:
        return _normalised(a) == _normalised(b)
    except Exception:
        return False


def _equivalent_header(a, b) -> bool:
    try:
        import copy

        a2, b2 = copy.copy(a), copy.copy(b)
        for f in _COMPOUND_BODIES:
            if hasattr(a2, f):
                setattr(a2, f, [])
                setattr(b2, f, [])
        return _normalised(a2) == _normalised(b2)
    except Exception:
        return False


_LITERAL_NODES = (ast.Constant, ast.operator, ast.cmpop, ast.boolop, ast.unaryop)


def _literal_only_change(ch) -> bool:
    """True when a changed import-time statement differs from its new version
    only in literals or operators (values change, structure does not)."""
    if ch.detail != "stmt" or ch.node is None or getattr(ch, "lambdas", None) is not None:
        return False
    b = getattr(ch, "new_node", None)
    if b is None:
        return False
    for node, path in _minimal_diffs(ch.node, b):
        if node is None:
            if not path or not isinstance(path[-1][0], ast.Constant):
                return False
        elif not isinstance(node, _LITERAL_NODES):
            return False
    return True


def _dict_keys_stable(a, b) -> bool:
    """True when assignments `a` and `b` both bind a dict literal with the
    same keys in the same order (no ** spread changed): only values differ."""
    va, vb = getattr(a, "value", None), getattr(b, "value", None)
    if not (isinstance(va, ast.Dict) and isinstance(vb, ast.Dict)) or len(va.keys) != len(vb.keys):
        return False
    for ka, kb, xa, xb in zip(va.keys, vb.keys, va.values, vb.values):
        if ka is None or kb is None:
            if ka is not kb or _dump(xa) != _dump(xb):
                return False
        elif _dump(ka) != _dump(kb):
            return False
    return True


def _literal_class_attr(st, inserted=False) -> bool:
    """`NAME = <value>` / `NAME: T = <value>` whose value has no calls: a
    removed one only stops binding NAME; an inserted one must not be able to
    raise, so it may hold constants (and containers of them) only."""
    if isinstance(st, ast.Assign):
        if len(st.targets) != 1 or not isinstance(st.targets[0], ast.Name):
            return False
        name, value = st.targets[0].id, st.value
    elif isinstance(st, ast.AnnAssign):
        if not isinstance(st.target, ast.Name) or st.value is None:
            return False
        name, value = st.target.id, st.value
    else:
        return False
    ok = (ast.Constant, ast.Tuple, ast.List, ast.Set, ast.Dict, ast.Load, ast.UnaryOp, ast.USub, ast.Not)
    if not inserted:
        ok += (ast.Name, ast.Attribute, ast.BinOp, ast.operator, ast.unaryop)
    nodes = list(ast.walk(value))
    if not all(isinstance(n, ok) for n in nodes):
        return False
    return not any(isinstance(n, ast.Name) and n.id == name for n in nodes)


def _changed_default_params(a, b):
    """Names of parameters whose default changed between FunctionDefs `a`
    and `b`, or None when anything else in the signature differs."""
    if a.name != b.name or [_dump(d) for d in a.decorator_list] != [_dump(d) for d in b.decorator_list]:
        return None
    if (_dump(a.returns) if a.returns else "") != (_dump(b.returns) if b.returns else ""):
        return None
    aa, ba = a.args, b.args
    for f in ("posonlyargs", "args", "kwonlyargs"):
        if [_dump(x) for x in getattr(aa, f)] != [_dump(x) for x in getattr(ba, f)]:
            return None
    if (_dump(aa.vararg) if aa.vararg else "") != (_dump(ba.vararg) if ba.vararg else ""):
        return None
    if (_dump(aa.kwarg) if aa.kwarg else "") != (_dump(ba.kwarg) if ba.kwarg else ""):
        return None
    if len(aa.defaults) != len(ba.defaults) or len(aa.kw_defaults) != len(ba.kw_defaults):
        return None
    pos = [x.arg for x in aa.posonlyargs + aa.args]
    changed = set()
    for i, (da, db) in enumerate(zip(aa.defaults, ba.defaults)):
        if _dump(da) != _dump(db):
            changed.add(pos[len(pos) - len(aa.defaults) + i])
    for x, da, db in zip(aa.kwonlyargs, aa.kw_defaults, ba.kw_defaults):
        if (_dump(da) if da else "") != (_dump(db) if db else ""):
            changed.add(x.arg)
    return changed or None


_ATTR_FUNCS = {"getattr", "hasattr", "setattr", "delattr", "attrgetter", "methodcaller", "signature",
               "getfullargspec", "__getattribute__", "__getattr__"}


def _attr_lookup_string(n) -> bool:
    """A string constant that may name an attribute: an argument of a
    getattr-style call, or anything not plainly a dict key / call argument."""
    p = getattr(n, "_rwx_parent", None)
    if isinstance(p, ast.Call):
        f = p.func
        fname = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        return fname is None or fname in _ATTR_FUNCS
    if isinstance(p, ast.Dict):
        return False
    if isinstance(p, ast.Compare):
        return False
    if isinstance(p, (ast.Tuple, ast.List, ast.Set)):
        q = getattr(p, "_rwx_parent", None)
        return not isinstance(q, (ast.Dict, ast.Compare, ast.Assign))
    return True


def _supplies(changed, params, kws, npos) -> bool:
    """True when a call with keyword names `kws` and `npos` positional
    arguments passes every parameter in `changed` explicitly."""
    for p in changed:
        if p in kws:
            continue
        if p in params and npos >= params.index(p) + 1:
            continue  # supplied positionally even if the call is unbound
        return False
    return True


def _names_class(v) -> bool:
    """`v` looks like a reference to a class (Foo, exp.Foo), not an object."""
    if isinstance(v, ast.Name):
        return v.id[:1].isupper()
    if isinstance(v, ast.Attribute):
        return v.attr[:1].isupper()
    return False


def _truth_only(n) -> bool:
    """`n` is evaluated only for its truth value."""
    p = getattr(n, "_rwx_parent", None)
    if isinstance(p, (ast.If, ast.While, ast.IfExp, ast.Assert)) and p.test is n:
        return True
    if isinstance(p, ast.UnaryOp) and isinstance(p.op, ast.Not):
        return True
    if isinstance(p, ast.comprehension) and any(c is n for c in p.ifs):
        return True
    if (isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and p.func.id == "bool"
            and len(p.args) == 1 and p.args[0] is n and not p.keywords):
        return True
    if isinstance(p, ast.BoolOp):
        return _truth_only(p)
    return False


def _key_only_use(n) -> bool:
    """A reference to a dict whose use depends only on its keys: `k in D`,
    `k not in D`, `len(D)`, or a truth test."""
    p = getattr(n, "_rwx_parent", None)
    if isinstance(p, ast.Compare):
        for op, c in zip(p.ops, p.comparators):
            if c is n:
                return isinstance(op, (ast.In, ast.NotIn))
        return False
    if (isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and p.func.id == "len"
            and len(p.args) == 1 and p.args[0] is n and not p.keywords):
        return True
    return _truth_only(n)


# entry points that parse SQL text (sqlglot.parse*, exp.maybe_parse, DataType.build, ...)
_SQL_TEXT_PARSERS = {"parse", "parse_one", "maybe_parse", "parse_identifier", "build", "to_table", "to_column"}


def _parsed_literal_change(ch) -> bool:
    """An import-time statement whose changed literal is an argument of a
    parse-like call (exp.maybe_parse("..."), parse_one("...")): the new text
    may not parse, and then importing the module raises."""
    b = getattr(ch, "new_node", None)
    if ch.node is None or b is None:
        return False
    for tree in (ch.node, b):
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f = n.func
                fname = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
                if fname in _SQL_TEXT_PARSERS and any(
                        isinstance(a, ast.Constant) and isinstance(a.value, str) for a in n.args):
                    return True
    return False


def _span(st):
    return (_start(st), getattr(st, "end_lineno", st.lineno))


class _Ctx:
    """Line-level knowledge from the patch: statements that do not touch a
    changed line are keyed by their exact text (cheap), touched ones by AST."""

    def __init__(self, a_src, b_src, a_changed, b_changed):
        self.a_lines = a_src.split("\n")
        self.b_lines = b_src.split("\n")
        self.a_changed = a_changed
        self.b_changed = b_changed

    def key(self, st, side):
        start, end = _span(st)
        changed = self.a_changed if side == "a" else self.b_changed
        lines = self.a_lines if side == "a" else self.b_lines
        if any(ln in changed for ln in range(start, end + 1)):
            return _shallow(st)
        return "T:" + "\n".join(lines[start - 1:end])

    def keys(self, body, side):
        return [self.key(st, side) for st in body]


def _refined(opcodes, a_body, b_body):
    """Statements next to a changed line are keyed by AST on the side whose
    line changed and by text on the other, so an insertion or deletion can
    show up as an unequal-length replace that swallows its neighbours.
    Re-match those ranges with the AST key on both sides."""
    for op, i1, i2, j1, j2 in opcodes:
        if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1) or i1 == i2 or j1 == j2:
            yield op, i1, i2, j1, j2
            continue
        sa = [_shallow(x) for x in a_body[i1:i2]]
        sb = [_shallow(x) for x in b_body[j1:j2]]
        sub = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
        for op2, k1, k2, l1, l2 in sub.get_opcodes():
            yield op2, i1 + k1, i1 + k2, j1 + l1, j1 + l2


def diff_body(kind, unit, a_body, b_body, parent_hdr, out: list, ctx: _Ctx):
    """Compare two statement lists (one unit).  Function/class definitions
    are compared by header only (their bodies are separate units)."""
    a_keys = ctx.keys(a_body, "a")
    b_keys = ctx.keys(b_body, "b")
    if a_keys == b_keys:
        return
    sm = difflib.SequenceMatcher(None, a_keys, b_keys, autojunk=False)
    for op, i1, i2, j1, j2 in _refined(sm.get_opcodes(), a_body, b_body):
        if op == "equal":
            continue
        if op == "replace" and (i2 - i1) == (j2 - j1):
            for a, b in zip(a_body[i1:i2], b_body[j1:j2]):
                diff_stmt(kind, unit, a, b, out, ctx)
            continue
        if i2 > i1:
            for a in a_body[i1:i2]:
                out.append(Change(kind, unit, [_span(a)], "stmt-removed/replaced", node=a))
            if j2 > j1 and kind != "function":
                out.append(Change(kind, unit, [_span(a) for a in a_body[i1:i2]], "stmt-added"))
        else:
            # pure insertion: whoever executes the neighbours reaches it
            nb = []
            if i1 > 0:
                nb.append(_span(a_body[i1 - 1]))
            if i1 < len(a_body):
                nb.append(_span(a_body[i1]))
            if not nb and parent_hdr:
                nb.append(parent_hdr)
            ins = Change(kind, unit, nb, "stmt-inserted")
            if kind == "class" and j2 - j1 == 1:
                ins.new_node = b_body[j1]
            out.append(ins)


def diff_stmt(kind, unit, a, b, out, ctx: _Ctx):
    # defs and classes are compared by header below (their bodies are units
    # of their own), so a full dump of them is never needed
    if type(a) is type(b) and not isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
            and _dump(a) == _dump(b):
        return
    if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef)) and type(a) is type(b):
        if _header_dump(a) == _header_dump(b):
            return  # body differs: handled as its own unit
        same_decorators = [_dump(d) for d in a.decorator_list] == [_dump(d) for d in b.decorator_list]
        if same_decorators and a.name == b.name:
            # defaults/annotations changed: only callers can observe it
            dch = Change("defaults", unit + ("." if unit else "") + a.name, [_span(a)], "signature", node=a)
            dch.new_node = b
            out.append(dch)
            if kind == "function":
                out.append(Change(kind, unit, [(_start(a), a.body[0].lineno - 1 if a.body else a.lineno)], "nested-def"))
            return
        out.append(Change(kind, unit, [_span(a)], "def-header", node=a))
        return
    if isinstance(a, ast.ClassDef) and isinstance(b, ast.ClassDef):
        if _header_dump(a) == _header_dump(b):
            return
        out.append(Change(kind, unit, [_span(a)], "class-header", node=a))
        return
    compound = any(getattr(a, f, None) for f in _COMPOUND_BODIES)
    if compound and type(a) is type(b):
        hdr = (a.lineno, _header_end(a))
        if _header_dump(a) != _header_dump(b) and not _equivalent_header(a, b):
            out.append(Change(kind, unit, [hdr], "header"))
        for f in _COMPOUND_BODIES:
            va, vb = getattr(a, f, None) or [], getattr(b, f, None) or []
            if f == "handlers" or f == "cases":
                if len(va) != len(vb):
                    out.append(Change(kind, unit, [_span(a)], f))
                    continue
                for ha, hb in zip(va, vb):
                    if f == "handlers":
                        ha_key = _dump(ha.type) if ha.type else ""
                        hb_key = _dump(hb.type) if hb.type else ""
                        if ha_key != hb_key or ha.name != hb.name:
                            out.append(Change(kind, unit, [(ha.lineno, ha.lineno)], "handler"))
                    else:
                        if _dump(ha.pattern) != _dump(hb.pattern) or _dump(ha.guard or ast.Pass()) != _dump(hb.guard or ast.Pass()):
                            out.append(Change(kind, unit, [(ha.pattern.lineno, ha.pattern.end_lineno)], "case"))
                    diff_body(kind, unit, ha.body, hb.body, (ha.lineno, ha.lineno) if f == "handlers" else hdr, out, ctx)
            else:
                diff_body(kind, unit, va, vb, hdr, out, ctx)
        return
    if _inert_string_stmt(a, b):
        return
    if kind in ("class", "module"):
        lams = _lambda_only(a, b)
        if lams:
            out.append(Change("function", unit, [(l.body.lineno, l.body.end_lineno) for l in lams], "lambda", lams))
            return
    if _equivalent_stmt(a, b):
        return
    ch = Change(kind, unit, [_span(a)], "stmt", node=a)
    ch.new_node = b
    out.append(ch)


def changed_lines(hunks):
    """Base-side and new-side line numbers touched by the hunks.  Insertion
    points mark the neighbouring lines on the base side."""
    a_changed, b_changed = set(), set()
    for os_, _ol, ns, _nl, body in hunks:
        a, b = os_, ns
        for hl in body:
            tag = hl[:1]
            if tag == " ":
                a += 1
                b += 1
            elif tag == "-":
                a_changed.add(a)
                a += 1
            elif tag == "+":
                b_changed.add(b)
                a_changed.add(a - 1)
                a_changed.add(a)
                b += 1
    return a_changed, b_changed


def _unit_span(node):
    if isinstance(node, ast.Module):
        return (1, 10 ** 9)
    return (_start(node), node.end_lineno)


def _inert_string_stmt(a, b) -> bool:
    """Both statements are bare string expressions whose edit nothing can
    observe: a string statement that is not a docstring is discarded, and a
    docstring is only seen through __doc__, which sqlglot reads solely to
    test for emptiness (doctests are not part of the collected suite)."""
    if not (isinstance(a, ast.Expr) and isinstance(b, ast.Expr)):
        return False
    va, vb = a.value, b.value
    if not (isinstance(va, ast.Constant) and isinstance(vb, ast.Constant)
            and isinstance(va.value, str) and isinstance(vb.value, str)):
        return False
    da, db = getattr(a, "_rwx_doc", False), getattr(b, "_rwx_doc", False)
    if da != db:
        return False
    return not da or (bool(va.value) and bool(vb.value))


def diff_module(base_src: str, new_src: str, hunks=None):
    """Return list[Change] or raise SyntaxError for the new source."""
    ta = ast.parse(base_src)
    tb = ast.parse(new_src)
    if hunks is None:
        a_changed = set(range(1, base_src.count("\n") + 2))
        b_changed = set(range(1, new_src.count("\n") + 2))
    else:
        a_changed, b_changed = changed_lines(hunks)
    ctx = _Ctx(base_src, new_src, a_changed, b_changed)
    ua, ub = Units(ta).units, Units(tb).units
    out: list[Change] = []
    for q, (kind, body, node) in ua.items():
        lo, hi = _unit_span(node)
        if not any(lo <= ln <= hi for ln in a_changed):
            continue
        if q not in ub:
            continue  # removed unit: its def statement shows up in the parent scope
        kb, bodyb, nodeb = ub[q]
        hdr = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            hdr = (_start(node), node.body[0].lineno - 1 if node.body else node.lineno)
        diff_body(kind, q, body, bodyb, hdr, out, ctx)
    return out


# ===================================================================== index
# The use trace reads only the pinned sources, so its results for every
# constant name of the pinned tree are precomputed (tools/build_trace_cache.py).
# The cache records a hash of the code below; any edit to it voids the cache.
TRACE_CODE = ("_trace_uses_live", "_index_file", "_in_slots", "_scope_of", "_key_only_use",
              "_truth_only", "_names_class", "_call_sites_live", "_attr_lookup_string",
              "static_imports", "collection_importers", "module_name")


def static_imports(rel: str, text: str) -> set:
    """Modules imported while `rel` is imported: import statements outside
    function bodies and outside `if TYPE_CHECKING:` blocks, with parent
    packages and `from pkg import submodule` candidates."""
    mod = Index.module_name(rel)
    pkg = mod if rel.endswith("__init__.py") else mod.rpartition(".")[0]
    out = set()

    def add(name):
        parts = name.split(".")
        for k in range(1, len(parts) + 1):
            out.add(".".join(parts[:k]))

    def walk(body):
        for st in body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(st, ast.Import):
                for a in st.names:
                    add(a.name)
            elif isinstance(st, ast.ImportFrom):
                if st.level:
                    parts = pkg.split(".") if pkg else []
                    if st.level > 1:
                        parts = parts[: len(parts) - (st.level - 1)]
                    base = ".".join(parts + ([st.module] if st.module else []))
                else:
                    base = st.module or ""
                if base:
                    add(base)
                    for a in st.names:
                        out.add(base + "." + a.name)
            elif isinstance(st, ast.If) and any(
                    (isinstance(n, ast.Name) and n.id == "TYPE_CHECKING")
                    or (isinstance(n, ast.Attribute) and n.attr == "TYPE_CHECKING") for n in ast.walk(st.test)):
                walk(st.orelse)
            else:
                for f in ("body", "orelse", "finalbody", "handlers"):
                    sub = getattr(st, f, None)
                    if sub:
                        if f == "handlers":
                            for h in sub:
                                walk(h.body)
                        else:
                            walk(sub)

    walk(ast.parse(text).body)
    return out


def collection_importers(sources: dict) -> dict:
    """module -> test files whose import (pytest collection) imports it."""
    mods = {Index.module_name(r): r for r in sources if r.endswith(".py")}
    graph = {m: {x for x in static_imports(r, sources[r]) if x in mods and x != m} for m, r in mods.items()}
    out: dict = {}
    for m, r in mods.items():
        if not (r.startswith("tests/") and r.rsplit("/", 1)[-1].startswith("test_")):
            continue
        seen = set()
        parts = m.split(".")
        todo = [".".join(parts[:k]) for k in range(1, len(parts) + 1) if ".".join(parts[:k]) in mods]
        while todo:
            x = todo.pop()
            if x in seen:
                continue
            seen.add(x)
            todo.extend(graph.get(x, ()))
        for x in seen:
            out.setdefault(x, []).append(r)
    return {k: sorted(v) for k, v in out.items()}


def trace_code_hash() -> str:
    import hashlib

    text = Path(__file__).read_text(encoding="utf-8")
    segs = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef) and node.name in TRACE_CODE:
            segs.append(node.name + "\n" + (ast.get_source_segment(text, node) or ""))
    return hashlib.sha256("\n".join(sorted(segs)).encode()).hexdigest()


_TRACE_CACHE: dict = {}


def _load_trace_cache(directory) -> dict:
    key = str(directory)
    if key not in _TRACE_CACHE:
        _TRACE_CACHE[key] = _read_trace_cache(directory)
    return _TRACE_CACHE[key]


def _read_trace_cache(directory) -> dict:
    if os.environ.get("RWX_NO_TRACE_CACHE"):
        return {}
    try:
        with gzip.open(directory / "trace_cache.json.gz", "rt", encoding="utf-8") as fh:
            blob = json.load(fh)
        if blob.get("code") != trace_code_hash():
            log("trace cache: code hash mismatch, ignored")
            return {}
        return blob["uses"]
    except Exception as e:  # missing or unreadable: trace live
        log("trace cache unavailable:", e)
        return {}


class Index:
    def __init__(self, tests: list[dict], directory: Path):
        with gzip.open(directory / "index.json.gz", "rt", encoding="utf-8") as fh:
            ix = json.load(fh)
        self.ix = ix
        number = {t["id"]: t["number"] for t in tests}
        self.by_file: dict[str, set] = {}
        for t in tests:
            self.by_file.setdefault(t["file"], set()).add(t["number"])
        # index test position -> test number in this run (None if absent)
        self.pos2num = [number.get(tid) for tid in ix["tests"]]
        self.sets = ix["sets"]
        self.mods = ix["mods"]
        self.lines = ix["lines"]
        self._set_cache: dict[int, frozenset] = {}
        self._sources = None
        self.directory = directory
        self.mod_files = {}
        for rel in ix["file_runtime"]:
            if rel.endswith(".py"):
                self.mod_files[self.module_name(rel)] = rel

    @staticmethod
    def module_name(rel: str) -> str:
        m = rel[:-3].replace("/", ".")
        if m.endswith(".__init__"):
            m = m[: -len(".__init__")]
        return m

    def sources(self):
        if self._sources is None:
            with gzip.open(self.directory / "source.json.gz", "rt", encoding="utf-8") as fh:
                self._sources = json.load(fh)
        return self._sources

    def tset(self, set_id: int) -> frozenset:
        s = self._set_cache.get(set_id)
        if s is None:
            s = self._set_cache[set_id] = frozenset(
                n for n in (self.pos2num[p] for p in self.sets[set_id]) if n is not None)
        return s

    def line_tests(self, rel: str, start: int, end: int):
        """(tests, import modules) of lines start..end of a file."""
        fl = self.lines.get(rel)
        tests, imods = set(), set()
        if not fl:
            return tests, imods
        for ln in range(start, end + 1):
            e = fl.get(str(ln))
            if e:
                tests |= self.tset(e[0])
                imods.update(self.mods[e[1]])
        return tests, imods

    def readers(self, rel: str) -> set:
        out = set()
        sid = self.ix["reads"].get(rel)
        if sid is not None:
            out |= self.tset(sid)
        mid = self.ix["reads_mods"].get(rel)
        if mid is not None:
            for m in self.mods[mid]:
                out |= self.module_users(m, deep=True)
        return out

    def class_users(self, module: str, qual: str) -> set:
        sid = self.ix["cls_users"].get(f"{module}:{qual}")
        return set(self.tset(sid)) if sid is not None else set()

    def import_instancers(self, module: str, qual: str) -> set:
        """Modules whose import instantiated class module:qual (or a
        subclass): a change that makes the instantiation raise breaks them."""
        mid = self.ix.get("cls_mods", {}).get(f"{module}:{qual}")
        return set(self.mods[mid]) if mid is not None else set()

    def import_broken_users(self, mods) -> set:
        out = set()
        for m in mods:
            out |= self.module_users(m, deep=True) | self.requirers(m)
        return out

    def classes_in(self, module: str):
        pre = module + ":"
        return [k for k in self.ix["cls_users"] if k.startswith(pre)]

    def module_users(self, module: str, deep: bool = False, _seen=None) -> set:
        """Tests that use a module: ran its code, instantiated its classes,
        and (deep) the same for modules that import it."""
        if _seen is None:
            _seen = set()
        if module in _seen:
            return set()
        _seen.add(module)
        out = set()
        rel = self.mod_files.get(module)
        if rel is not None:
            out |= self.tset(self.ix["file_runtime"][rel])
        for k in self.classes_in(module):
            out |= self.tset(self.ix["cls_users"][k])
        for f in self.ix["collect_imports"].get(module, ()):
            out |= self.file_tests(f)
        if deep:
            for imp in self.ix["importers"].get(module, ()):
                out |= self.module_users(imp, True, _seen)
        return out

    def requirers(self, module: str) -> set:
        """Tests that (transitively) import the module, even from cache: if
        importing it raises, all of them fail."""
        sid = self.ix.get("requirers", {}).get(module)
        out = set(self.tset(sid)) if sid is not None else set()
        return out | self.collectors(module)

    _collect_files = None

    def collectors(self, module: str) -> set:
        """Every test of each test file whose collection imports the module
        (pinned-source import graph): an import error there fails them all."""
        if self._collect_files is None:
            Index._collect_files = _load_trace_cache(self.directory).get("__collect__", {})
            if not Index._collect_files:
                Index._collect_files = collection_importers(self.sources())
        out = set()
        for f in self._collect_files.get(module, ()):
            out |= self.by_file.get(f, set())
        return out

    def file_tests(self, test_file: str) -> set:
        sid = self.ix["file_runtime"].get(test_file)
        return set(self.tset(sid)) if sid is not None else set()


# ===================================================================== selector
class Selector:
    def __init__(self, tests: list[dict], index_dir: Path = INDEX_DIR):
        self.tests = tests
        self.by_number = {t["number"]: t for t in tests}
        self.all_ids = set(self.by_number)
        self.by_file: dict[str, set] = {}
        for t in tests:
            self.by_file.setdefault(t["file"], set()).add(t["number"])
        self.index = Index(tests, index_dir)
        global _SOURCES_FOR_ENUMS
        _SOURCES_FOR_ENUMS = self.index.sources

    # ------------------------------------------------------------ fallbacks
    def broad_for_path(self, rel: str) -> set:
        """Safe answer when a file cannot be analysed."""
        ix = self.index
        if rel.endswith(".py"):
            mod = ix.module_name(rel)
            users = ix.module_users(mod, deep=True) | ix.readers(rel) | ix.requirers(mod)
            if rel.startswith("tests/") and rel in self.by_file:
                users |= self.by_file[rel]
            return users or set(self.all_ids)
        return set(self.all_ids)

    # ------------------------------------------------------------ python
    def python_change(self, rel: str, fd: FileDiff, reasons: list) -> set:
        ix = self.index
        src = ix.sources()
        base = src.get(fd.old) if fd.old else None
        mod = ix.module_name(rel)
        sel = set()
        if fd.new is None:  # deleted module
            reasons.append(f"deleted:{rel}")
            return self.broad_for_path(rel)
        if base is None:
            if fd.old is not None:
                reasons.append(f"unknown-base:{rel}")
                return self.broad_for_path(rel)
            # brand new file: only code that discovers files can see it
            parent = rel.rsplit("/", 1)[0]
            reasons.append(f"new-file:{rel}")
            return ix.readers(parent) | ix.readers(rel)
        try:
            new_src = apply_hunks(base, fd.hunks)
        except ValueError:
            reasons.append(f"apply-failed:{rel}")
            return self.broad_for_path(rel)
        if fd.old != fd.new:  # rename: module path changes, importers break
            reasons.append(f"rename:{rel}")
            return self.broad_for_path(rel) | self.broad_for_path(fd.new) if fd.new.endswith(".py") else self.broad_for_path(rel)
        try:
            changes = diff_module(base, new_src, fd.hunks)
        except SyntaxError:
            reasons.append(f"syntax-error:{rel}")
            return self.broad_for_path(rel)
        if base != new_src:
            sel |= ix.readers(rel)  # tests reading the source text itself
        if not changes:
            reasons.append(f"ast-equal:{rel}")
            return sel
        for ch in changes:
            got = self._change_tests(rel, mod, ch)
            reasons.append(f"{ch.kind}:{ch.unit}:{ch.detail}:{len(got)}")
            sel |= got
        return sel

    def _change_tests(self, rel, mod, ch: Change) -> set:
        ix = self.index
        out = set()
        if ch.kind == "function":
            for a, b in ch.lines:
                ts, imods = ix.line_tests(rel, a, b)
                out |= ts
                if ch.detail == "lambda":
                    # the lambda's lines are shared with the statement that
                    # creates it at import; its body only runs when called
                    imods = {m for m in imods if m != mod}
                for m in imods:  # this code also runs while some module imports:
                    # a raise there breaks every importer
                    out |= ix.module_users(m, deep=True) | ix.requirers(m)
            return out
        if ch.kind == "defaults":
            # only calls of this function see new defaults/annotations
            for a, b in ch.lines:
                ts, imods = ix.line_tests(rel, a, b)
                out |= ts
                for m in imods:
                    if m != mod:
                        # called while m imports: a raise breaks m's importers
                        out |= ix.module_users(m, deep=True) | ix.collectors(m)
            # ... and of those, only calls that leave a changed parameter out
            narrowed = self._narrow_defaults(ch)
            if narrowed is not None:
                out &= narrowed
            return out
        if ch.kind == "class" and ch.detail in ("stmt-removed/replaced", "stmt-inserted"):
            # a literal class attribute removed (base value shows through) or
            # added (overrides the base): only reads of that name through
            # this class can tell
            st = ch.node if ch.detail == "stmt-removed/replaced" else ch.new_node
            if _literal_class_attr(st, inserted=ch.detail == "stmt-inserted"):
                probe = Change(ch.kind, ch.unit, ch.lines, "removed" if ch.detail == "stmt-removed/replaced" else "stmt", node=st)
                narrowed = self._narrow_by_name(rel, mod, probe)
                if narrowed is not None:
                    return narrowed
        structural = not _literal_only_change(ch)
        if structural or _parsed_literal_change(ch):
            # anything but a literal/operator tweak can make the import raise,
            # and so can SQL text parsed while the module imports
            out |= ix.requirers(mod)
        narrowed = None if structural else self._narrow_dict_entry(mod, ch)
        if narrowed is None and not structural:
            narrowed = self._narrow_by_name(rel, mod, ch)
        if narrowed is not None:
            return narrowed
        # import-time statement in a class or module body
        for a, b in ch.lines:
            ts, imods = ix.line_tests(rel, a, b)
            out |= ts
            for m in imods:
                if m != mod:
                    out |= ix.module_users(m, deep=True)
                    if structural:
                        out |= ix.requirers(m)
        if ch.kind == "class":
            q = ch.unit.split("#", 1)[0]
            out |= ix.class_users(mod, q)
            # instances built while some module imports (e.g. SQL templates
            # parsed in a class body) see the change at import time
            out |= ix.import_broken_users(self._nested_instancers(mod, q))
            # tests that executed any method of the class (or nested class)
            out |= self._class_runtime(rel, mod, q)
            # subclass users elsewhere are included via MRO in class_users;
            # attributes copied by metaclasses into sibling classes of the
            # same module (e.g. Dialect -> its Tokenizer/Parser) are covered
            # by also taking users of classes nested under the outer class.
            outer = q.split(".", 1)[0]
            for k in ix.classes_in(mod):
                cq = k.split(":", 1)[1]
                if cq == outer or cq.startswith(outer + "."):
                    out |= ix.tset(ix.ix["cls_users"][k])
            if not out:
                out |= ix.module_users(mod, deep=True)
        else:
            out |= ix.module_users(mod, deep=True)
        return out

    def _narrow_defaults(self, ch: Change):
        """Only a call that leaves a parameter out sees that parameter's new
        default.  Every reference to the function's name must be a direct
        call (a callback, getattr string or inspect use disables this); the
        answer is the tests executing calls that may omit a changed
        parameter.  Positional arguments count as supplying a parameter only
        when they do so whether or not the call is bound."""
        a, b = ch.node, ch.new_node
        if a is None or b is None:
            return None
        if a.name.startswith("__") and a.name.endswith("__"):
            return None  # called implicitly (ClassName(...), operators, protocols)
        for d in a.decorator_list:
            if not (isinstance(d, ast.Name) and d.id in ("staticmethod", "classmethod")):
                return None  # a wrapper or registry may call it on its own terms
        changed = _changed_default_params(a, b)
        if not changed:
            return None
        params = [x.arg for x in a.args.posonlyargs + a.args.args]
        sites = self._call_sites(a.name)
        if sites is None:
            return None
        ix = self.index
        out = set()
        for frel, lo, hi, kws, npos, star in sites:
            if star or not _supplies(changed, params, set(kws), npos):
                ts, imods = ix.line_tests(frel, lo, hi)
                out |= ts
                for m in imods:
                    out |= ix.module_users(m, deep=True) | ix.requirers(m)
        return out

    def _call_sites(self, name):
        if self._trace_cache is None:
            Selector._trace_cache = _load_trace_cache(self.index.directory)
        hit = self._trace_cache.get("call:" + name)
        if hit is not None:
            return hit[0]
        return self._call_sites_live(name)

    def _call_sites_live(self, name):
        """Every reference to `name` as (file, first line, last line, keyword
        names, positional count, has */**), or None when some reference is
        not a direct call (callback, assignment, getattr-style string)."""
        out = []
        for frel, text in sorted(self.index.sources().items()):
            if name not in text:
                continue
            for n in self._named_nodes(frel).get(name, ()):
                if isinstance(n, ast.arg) or (isinstance(n, ast.keyword) and n.arg == name):
                    continue
                if isinstance(n, ast.Constant):
                    if n.value == name and _attr_lookup_string(n):
                        return None
                    continue
                if not ((isinstance(n, ast.Name) and n.id == name) or (isinstance(n, ast.Attribute) and n.attr == name)):
                    continue
                par = getattr(n, "_rwx_parent", None)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    return None
                if not (isinstance(par, ast.Call) and par.func is n):
                    return None
                star = any(isinstance(x, ast.Starred) for x in par.args) or any(k.arg is None for k in par.keywords)
                out.append([frel, par.lineno, getattr(par, "end_lineno", par.lineno),
                            sorted(k.arg for k in par.keywords if k.arg), len(par.args), star])
        out.sort()
        return out

    def _expr_class_users(self, name: str):
        """Tests that instantiated sqlglot expression class `name` (or a
        subclass, via the recorded MRO). None if the name is not a class."""
        ix = self.index
        hit = None
        for k, sid in ix.ix["cls_users"].items():
            m, _, q = k.partition(":")
            if q == name and m.startswith("sqlglot.expressions"):
                hit = (hit or set()) | ix.tset(sid)
        if hit is None and self._is_expr_class(name):
            return set()
        return hit

    def _is_expr_class(self, name):
        pat = re.compile(r"^class\s+" + re.escape(name) + r"\s*\(", re.M)
        return any(pat.search(t) for f, t in self.index.sources().items() if f.startswith("sqlglot/expressions/"))

    def _narrow_dict_entry(self, mod, ch: Change):
        """Changed values of a dict keyed by expression classes (TRANSFORMS,
        type metadata, ...) only matter when such an expression exists."""
        a, b = ch.node, ch.new_node
        if a is None or b is None or not isinstance(a, (ast.Assign, ast.AnnAssign)):
            return None
        da, db = a.value, b.value
        if not (isinstance(da, ast.Dict) and isinstance(db, ast.Dict)) or len(da.keys) != len(db.keys):
            return None
        keys = []
        for ka, kb, va, vb in zip(da.keys, db.keys, da.values, db.values):
            if (_dump(ka) if ka else "**") != (_dump(kb) if kb else "**"):
                return None
            if _dump(va) == _dump(vb):
                continue
            if ka is None:
                return None  # a spread (**BASE) changed
            if isinstance(ka, ast.Attribute):
                keys.append(ka.attr)
            elif isinstance(ka, ast.Name):
                keys.append(ka.id)
            else:
                return None
        if not keys:
            return None
        out = set()
        for k in keys:
            users = self._expr_class_users(k)
            if users is None:
                return None
            out |= users
        if ch.kind == "class":
            out &= self.index.class_users(mod, ch.unit.split("#", 1)[0]) | self._nested_users(mod, ch.unit)
            # an import that builds both the owner and such an expression
            owner = self._nested_instancers(mod, ch.unit.split("#", 1)[0])
            keyed = set()
            for k in keys:
                keyed |= self._expr_class_instancers(k)
            out |= self.index.import_broken_users(owner & keyed)
        else:
            out &= self.index.module_users(mod, deep=True)
        return out

    def _expr_class_instancers(self, name: str) -> set:
        out = set()
        for k, mid in self.index.ix.get("cls_mods", {}).items():
            m, _, q = k.partition(":")
            if q == name and m.startswith("sqlglot.expressions"):
                out.update(self.index.mods[mid])
        return out

    def _nested_instancers(self, mod, unit) -> set:
        """import_instancers of the class and of classes nested under its
        outermost class (metaclass-copied attributes, see _nested_users)."""
        ix = self.index
        q = unit.split("#", 1)[0]
        outer = q.split(".", 1)[0]
        out = ix.import_instancers(mod, q)
        pre = mod + ":"
        for k in ix.ix.get("cls_mods", {}):
            if k.startswith(pre):
                cq = k[len(pre):]
                if cq == outer or cq.startswith(outer + "."):
                    out |= ix.import_instancers(mod, cq)
        return out

    def _nested_users(self, mod, unit):
        ix = self.index
        outer = unit.split("#", 1)[0].split(".", 1)[0]
        out = set()
        for k in ix.classes_in(mod):
            cq = k.split(":", 1)[1]
            if cq == outer or cq.startswith(outer + "."):
                out |= ix.tset(ix.ix["cls_users"][k])
        return out

    def _narrow_by_name(self, rel, mod, ch: Change):
        """A changed constant can only change behaviour where its value is
        *used*.  Follow exact pass-throughs (x = self.NAME, f(k=self.NAME),
        self.k = k) and collect every other reference; the answer is the tests
        executing those uses (and, for class attributes, using the class).
        Any import-time reference, dynamic string reference or untraceable
        hand-off disables the narrowing (returns None -> broad rule)."""
        node = ch.node
        if node is None or ch.kind not in ("class", "module"):
            return None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets, value = [node.target], node.value
        else:
            return None
        names = set()
        for t in targets:
            if not isinstance(t, ast.Name):
                return None
            names.add(t.id)
        if not names or value is None:
            return None
        for sub in ast.walk(value):
            if isinstance(sub, (ast.Lambda, ast.Call, ast.NamedExpr)):
                return None
        # a removed binding can make any reference raise, pass-throughs included
        uses = self._trace_uses(names, keys_stable=_dict_keys_stable(node, ch.new_node),
                                every_ref=ch.detail == "removed")
        if uses is None:
            return None
        ix = self.index
        out = set()
        for frel, lno in uses:
            ts, imods = ix.line_tests(frel, lno, lno)
            if imods:
                return None
            out |= ts
        if ch.kind == "class" and not self._static_ref:
            # every read goes through an object; it must belong to the class
            users = ix.class_users(mod, ch.unit.split("#", 1)[0]) | self._nested_users(mod, ch.unit)
            if not users:
                return None
            out &= users
        return out

    _ast_cache: dict = {}
    _names_cache: dict = {}

    def _tree(self, frel):
        t = self._ast_cache.get(frel)
        if t is None:
            self._index_file(frel)
            t = self._ast_cache[frel]
        return t

    def _named_nodes(self, frel):
        """identifier -> nodes that can mention it (Name, Attribute, str
        Constant, arg, keyword); built once per file."""
        d = self._names_cache.get(frel)
        if d is None:
            self._index_file(frel)
            d = self._names_cache[frel]
        return d

    def _index_file(self, frel):
        """Parse once; set parent links and build the identifier table in a
        single pass over the tree."""
        t = ast.parse(self.index.sources()[frel])
        d = {}
        AST, Name, Attribute, Constant, arg, keyword = ast.AST, ast.Name, ast.Attribute, ast.Constant, ast.arg, ast.keyword
        stack = [t]
        pop, push = stack.pop, stack.append
        while stack:
            node = pop()
            for f in node._fields:
                v = getattr(node, f, None)
                if type(v) is list:
                    for c in v:
                        if isinstance(c, AST):
                            c._rwx_parent = node
                            push(c)
                elif isinstance(v, AST):
                    v._rwx_parent = node
                    push(v)
            tp = type(node)
            if tp is Name:
                k = node.id
            elif tp is Attribute:
                k = node.attr
            elif tp is Constant:
                k = node.value
                if type(k) is not str:
                    continue
            elif tp is arg:
                k = node.arg
            elif tp is keyword:
                k = node.arg
                if not k:
                    continue
            else:
                continue
            lst = d.get(k)
            if lst is None:
                d[k] = [node]
            else:
                lst.append(node)
        self._ast_cache[frel] = t
        self._names_cache[frel] = d

    _trace_cache = None

    def _cached_trace(self, start_names, keys_stable, every_ref):
        if self._trace_cache is None:
            Selector._trace_cache = _load_trace_cache(self.index.directory)
        if len(start_names) != 1:
            return False, None
        (name,) = start_names
        hit = self._trace_cache.get(f"{name}|{int(keys_stable)}{int(every_ref)}")
        if hit is None:
            return False, None
        uses, static = hit
        self._static_ref = static
        return True, (None if uses is None else {tuple(u) for u in uses})

    def _trace_uses(self, start_names, keys_stable=False, every_ref=False):
        found, res = self._cached_trace(start_names, keys_stable, every_ref)
        if found:
            return res
        return self._trace_uses_live(start_names, keys_stable, every_ref)

    def _trace_uses_live(self, start_names, keys_stable=False, every_ref=False):
        ix = self.index
        src = ix.sources()
        names = set(start_names)
        todo = list(start_names)
        uses = set()
        defined_params = set()
        handed = set()
        self._static_ref = False
        while todo:
            name = todo.pop()
            files = [f for f, text in src.items() if name in text]
            if len(files) > 25:
                return None
            for frel in files:
                for n in self._named_nodes(frel).get(name, ()):
                    hit = ((isinstance(n, ast.Name) and n.id == name)
                           or (isinstance(n, ast.Attribute) and n.attr == name)
                           or (isinstance(n, ast.Constant) and n.value == name))
                    if isinstance(n, ast.arg) and n.arg == name:
                        defined_params.add(name)
                        continue
                    if isinstance(n, ast.keyword) and n.arg == name:
                        continue  # receiving side of a pass-through
                    if not hit:
                        continue
                    par = getattr(n, "_rwx_parent", None)
                    if isinstance(n, ast.Attribute) and _names_class(n.value):
                        self._static_ref = True  # Foo.NAME: read without an instance
                    if isinstance(n, ast.Constant):
                        if self._in_slots(n):
                            continue
                        return None  # getattr(..., "NAME") style access
                    # class/module level (re)definition of the same name
                    if isinstance(par, (ast.Assign, ast.AnnAssign)) and n in (getattr(par, "targets", None) or [getattr(par, "target", None)]):
                        scope = self._scope_of(par)
                        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                            continue
                        # assignment target inside a function: store, not a read
                        continue
                    if isinstance(par, ast.AnnAssign) and par.value is None:
                        continue
                    # pass-through: k=<ref> or x = <ref>
                    if isinstance(par, ast.keyword) and par.value is n and par.arg:
                        if par.arg not in names:
                            names.add(par.arg)
                            todo.append(par.arg)
                        handed.add(par.arg)
                        uses.add((frel, n.lineno, "pass"))
                        continue
                    if isinstance(par, ast.Assign) and par.value is n and len(par.targets) == 1:
                        tgt = par.targets[0]
                        tname = tgt.id if isinstance(tgt, ast.Name) else tgt.attr if isinstance(tgt, ast.Attribute) else None
                        if tname is None:
                            return None
                        if tname not in names:
                            names.add(tname)
                            todo.append(tname)
                        uses.add((frel, n.lineno, "pass"))
                        continue
                    if keys_stable and _key_only_use(n):
                        continue  # membership/truthiness/len: same keys, same answer
                    uses.add((frel, n.lineno, "use"))
        # a keyword hand-off must land in a real parameter we can see
        if any(k not in defined_params for k in handed):
            return None
        # pass-throughs only move the value; every place it is consumed is a
        # "use" line, and uses executed at import time disable the narrowing
        if every_ref:
            return {(frel, lno) for frel, lno, kind in uses}
        return {(frel, lno) for frel, lno, kind in uses if kind == "use"}

    @staticmethod
    def _scope_of(node):
        p = getattr(node, "_rwx_parent", None)
        while p is not None and not isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef, ast.Module)):
            p = getattr(p, "_rwx_parent", None)
        return p

    @staticmethod
    def _in_slots(n):
        p = getattr(n, "_rwx_parent", None)
        while p is not None and not isinstance(p, ast.stmt):
            p = getattr(p, "_rwx_parent", None)
        return isinstance(p, (ast.Assign, ast.AnnAssign)) and any(
            isinstance(t, ast.Name) and t.id == "__slots__"
            for t in (getattr(p, "targets", None) or [getattr(p, "target", None)]))

    def _class_runtime(self, rel, mod, qual) -> set:
        src = self.index.sources().get(rel)
        out = set()
        if src is None:
            return out
        tree = ast.parse(src)
        node = tree
        for part in qual.split("."):
            nxt = None
            for st in getattr(node, "body", []):
                if isinstance(st, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and st.name == part:
                    nxt = st
            if nxt is None:
                return out
            node = nxt
        for st in ast.walk(node):
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)) and st.body:
                ts, _ = self.index.line_tests(rel, st.body[0].lineno, st.end_lineno)
                out |= ts
        return out

    # ------------------------------------------------------------ data files
    def data_change(self, fd: FileDiff, reasons: list) -> set:
        ix = self.index
        sel = set()
        for p in {fd.old, fd.new} - {None}:
            sel |= ix.readers(p)
            if fd.old is None or fd.new is None or fd.old != fd.new:
                # file appears/disappears: code that lists its directory sees it
                parts = p.split("/")
                for k in range(1, len(parts)):
                    sel |= self._dir_readers("/".join(parts[:k]))
        reasons.append(f"data:{fd.path}:{len(sel)}")
        return sel

    def _dir_readers(self, d):
        ix = self.index
        sid = ix.ix["reads"].get(d)
        return set(ix.tset(sid)) if sid is not None else set()

    # ------------------------------------------------------------ entry
    def for_patch(self, patch: str, reasons: list | None = None) -> set:
        if reasons is None:
            reasons = []
        try:
            files = parse_patch(patch)
        except ValueError as e:
            reasons.append(f"unparseable:{e}")
            return set(self.all_ids)
        sel = set()
        for fd in files:
            rel = fd.path
            if rel is None:
                continue
            try:
                if fd.binary:
                    sel |= self.data_change(fd, reasons)
                elif rel.endswith(".py") and (rel.startswith("sqlglot/") or rel.startswith("tests/")):
                    sel |= self.python_change(rel, fd, reasons)
                elif rel.endswith(".py"):
                    sel |= self.index.readers(rel)
                    reasons.append(f"py-outside:{rel}")
                else:
                    sel |= self.data_change(fd, reasons)
            except Exception as e:  # never crash: fail safe
                reasons.append(f"error:{rel}:{type(e).__name__}:{e}")
                sel |= self.broad_for_path(rel)
        return sel & self.all_ids


# ===================================================================== schedule
def _dur(lookup, n) -> int:
    return round(lookup[n]["seconds"] * 1000)


def schedule(ids, lookup) -> list[list[int]]:
    """Choose worker count and assignment minimising max load + 2 s/worker.
    LPT for every k, then a small local search on the best few k."""
    if not ids:
        return []
    ms = {n: _dur(lookup, n) for n in ids}
    items = sorted(ids, key=lambda n: (-ms[n], n))
    durs = [ms[n] for n in items]
    total = sum(durs)
    best = None
    for k in range(1, min(MAX_WORKERS, len(items)) + 1):
        lb = max(durs[0], -(-total // k)) + WORKER_COST_MS * k
        if best is not None and lb >= best[0]:
            continue
        loads = [0] * k
        buckets = [[] for _ in range(k)]
        for n, d in zip(items, durs):
            w = min(range(k), key=lambda i: (loads[i], i))
            buckets[w].append(n)
            loads[w] += d
        buckets, loads = _improve(buckets, loads, ms)
        cost = max(loads) + WORKER_COST_MS * k
        if best is None or cost < best[0]:
            best = (cost, buckets)
    return [sorted(b) for b in best[1] if b]


def _improve(buckets, loads, ms, rounds=50):
    """Move/swap single tests out of the most loaded worker while it helps.
    `ms` maps test number -> duration in ms."""
    k = len(buckets)
    if k < 2:
        return buckets, loads
    for _ in range(rounds):
        hi = max(range(k), key=lambda i: loads[i])
        improved = False
        for lo in sorted(range(k), key=lambda i: loads[i]):
            if lo == hi:
                continue
            gap = loads[hi] - loads[lo]
            # move
            for n in sorted(buckets[hi], key=lambda x: -ms[x]):
                d = ms[n]
                if 0 < d < gap:
                    buckets[hi].remove(n)
                    buckets[lo].append(n)
                    loads[hi] -= d
                    loads[lo] += d
                    improved = True
                    break
            if improved:
                break
            # swap: first (n, m) in list order with dn - gap < dm < dn
            lo_d = [ms[m] for m in buckets[lo]]
            if not lo_d:
                continue
            lo_min, lo_max = min(lo_d), max(lo_d)
            for n in buckets[hi]:
                dn = ms[n]
                if lo_min >= dn or lo_max <= dn - gap:
                    continue  # no m of this worker can qualify
                for m, dm in zip(buckets[lo], lo_d):
                    if 0 < dn - dm < gap:
                        buckets[hi].remove(n)
                        buckets[lo].remove(m)
                        buckets[hi].append(m)
                        buckets[lo].append(n)
                        loads[hi] += dm - dn
                        loads[lo] += dn - dm
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
        if not improved:
            break
    return buckets, loads


# ===================================================================== verify
T0 = __import__("time").monotonic()
VERIFY_ALL = os.environ.get("RWX_VERIFY_ALL") == "1"   # validation: verify every eligible commit
VERIFY_DUMP = os.environ.get("RWX_VERIFY_DUMP")        # validation: write observed passes here
VERIFY_OVERHEAD_S = 0.15   # fork + fresh sqlglot/test-module imports, per commit
VERIFY_CLASS_SETUP_S = {"tests/test_executor.py": 1.5}  # setUpClass work not in catalog seconds
VERIFY_CPU_SCALE = 2.2     # scorer CPU vs the machine the estimates were measured on
                           # (v3: 1.00 s here, 2.49 s on the board; v4: 0.387 s vs 0.92 s)
VERIFY_REEXEC_FRAC = 0.5   # share of a proxied test's saving that re-execution may spend
VERIFY_GAIN_FRAC = 0.7     # run only when estimated CPU <= this share of the cost it can save
VERIFY_WALL_S = float(os.environ.get("RWX_VERIFY_WALL", "100"))


def _cost_ms(ids, lookup) -> int:
    w = schedule(ids, lookup)
    if not w:
        return 0
    return max(sum(_dur(lookup, n) for n in b) for b in w) + WORKER_COST_MS * len(w)


REPLAY_EST_S = {"tpcds_execute": 3.0, "tpch_execute": 0.3, "tpch_optimized": 0.2}  # child CPU, measured


def _replay_cov():
    try:
        with gzip.open(INDEX_DIR / "replay_cov.json.gz", "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def replay_eligible(select, files, proxied_ids, lookup, cov) -> dict:
    """Proxied tests whose outcome the replay decides for this patch, mapped
    to the query positions that must be re-executed for real.  Requires that
    every change is a statement inside a function body of a sqlglot module,
    that none of it runs at import time, and that none of it is executed by
    the test's shared phase 2 (class fixtures) on the pinned tree."""
    if not proxied_ids or cov is None or select is None:
        return {}
    spans = []
    src = select.index.sources()
    for fd in files:
        rel = fd.old
        if not rel.startswith("sqlglot/"):
            return {}
        base = src.get(rel)
        if base is None:
            return {}
        try:
            new_src = apply_hunks(base, fd.hunks)
            changes = diff_module(base, new_src, fd.hunks)
        except (ValueError, SyntaxError):
            return {}
        for ch in changes:
            if ch.kind != "function":
                return {}
            for a, b in ch.lines:
                _, imods = select.index.line_tests(rel, a, b)
                if imods:
                    return {}
                spans.append((rel, a, b))

    def hit(lines):
        return any(any(a <= ln <= b for ln in lines.get(rel, ())) for rel, a, b in spans)

    out = {}
    for n in proxied_ids:
        c = cov.get(lookup[n]["id"])
        if c is None or hit(c["shared"]):
            continue
        out[n] = sorted(int(q) for q, lines in c["per"].items() if hit(lines))
    return out


def verify(chosen, lookup, select=None):
    """Drop candidate tests that a forked child observed passing on the
    patched tree, or whose outcome an exact phase-1 replay proves unchanged."""
    sys.path.insert(0, str(HERE))
    import runner
    if not runner.available():
        return chosen
    import replay
    proxy_kind = {}
    for n, t in lookup.items():
        k = replay.PROXIES.get(t["id"])
        if k:
            proxy_kind[n] = k
    cov = None
    jobs = []
    for i, (stem, ids, text) in enumerate(chosen):
        if not ids:
            continue
        try:
            files = parse_patch(text)
        except ValueError:
            continue
        patched = runner.patched_sources(files, apply_hunks)
        if patched is None:
            continue
        proxied = {n for n in ids if n in proxy_kind}
        elig = {}
        if proxied:
            if cov is None:
                cov = _replay_cov() or {}
            elig = replay_eligible(select, files, proxied, lookup, cov)
        base_ms = _cost_ms(ids, lookup)
        replays = []
        keep = ids
        if elig:
            rest = ids - set(elig)
            save_s = (base_ms - _cost_ms(rest, lookup)) / 1000
            r_est = sum(REPLAY_EST_S[proxy_kind[n]] for n in elig) * VERIFY_CPU_SCALE
            if VERIFY_ALL or r_est <= VERIFY_GAIN_FRAC * save_s:
                secs_of = {n: cov[lookup[n]["id"]]["secs"] for n in elig}
                max_s = 600.0 if VERIFY_ALL else VERIFY_REEXEC_FRAC * save_s / VERIFY_CPU_SCALE
                replays = []
                for n in sorted(elig):
                    forced = elig[n]
                    if forced and 1.5 + sum(secs_of[n].get(str(q), 1.0) for q in forced) > max_s:
                        continue  # re-executing what the change reaches costs more than it saves
                    replays.append((n, proxy_kind[n], forced, secs_of[n], max_s))
                keep = ids - {r[0] for r in replays}
        r_tests = keep - proxied
        run_s = sum(lookup[n]["seconds"] for n in r_tests)
        files_c = {lookup[n]["file"] for n in r_tests}
        est = (VERIFY_OVERHEAD_S + run_s + sum(VERIFY_CLASS_SETUP_S.get(f, 0) for f in files_c)) * VERIFY_CPU_SCALE
        save = (_cost_ms(keep, lookup) - _cost_ms(keep - r_tests, lookup)) / 1000
        if VERIFY_ALL:
            if run_s > float(os.environ.get("RWX_VERIFY_MAXS", "1e9")):
                r_tests = set()
        elif not r_tests or est > VERIFY_GAIN_FRAC * save:
            r_tests = set()
        if not r_tests and not replays:
            continue
        tests = sorted((lookup[n] for n in r_tests), key=lambda t: t["number"])
        rp = replays
        budget = 600.0 if VERIFY_ALL else 4.0 + 3.0 * (run_s + sum(REPLAY_EST_S[r[1]] + r[4] for r in rp))
        jobs.append((i, tests, patched, budget, rp))
    if not jobs:
        return chosen
    # cheapest first, so a slow machine still verifies the most commits
    jobs.sort(key=lambda j: sum(t["seconds"] for t in j[1]) + sum(REPLAY_EST_S[r[1]] for r in j[4]))
    deadline = None if VERIFY_ALL else T0 + VERIFY_WALL_S
    passed = runner.run_jobs(jobs, parallel=int(os.environ.get("RWX_VERIFY_PAR", "2")), deadline=deadline)
    if VERIFY_DUMP:
        with open(VERIFY_DUMP, "w") as fh:
            json.dump({chosen[i][0]: {"passed": sorted(p), "kept": runner.run_jobs.kept.get(i),
                                    "cpu": runner.run_jobs.cpu.get(i)}
                       for i, p in passed.items()}, fh)
    out = list(chosen)
    for i, p in passed.items():
        stem, ids, text = out[i]
        out[i] = (stem, ids - p, text)
        log("verify", stem, len(ids), "->", len(ids - p))
    return out


# ===================================================================== main
def main() -> None:
    tests = json.loads((DATA / "tests.json").read_text(encoding="utf-8"))["tests"]
    patches = sorted((DATA / "commits").glob("*.patch"))
    out_lines = []
    try:
        select = Selector(tests)
    except Exception as e:  # index unusable: everything, still valid output
        print(f"index load failed: {e}", file=sys.stderr)
        select = None
    all_ids = {t["number"] for t in tests}
    lookup = {t["number"]: t for t in tests}
    chosen = []
    for patch in patches:
        reasons: list = []
        text = ""
        try:
            text = patch.read_bytes().decode("utf-8", errors="replace")
            ids = select.for_patch(text, reasons) if select else set(all_ids)
        except Exception as e:
            reasons.append(f"fatal:{e}")
            ids = set(all_ids)
        log(patch.stem, len(ids), reasons)
        chosen.append((patch.stem, ids, text))
    try:
        chosen = verify(chosen, lookup, select)
    except Exception as e:  # verification is an optimisation only
        print(f"verify failed: {e}", file=sys.stderr)
    for stem, ids, _ in chosen:
        workers = schedule(ids, lookup)
        out_lines.append(json.dumps({"commit": stem, "workers": workers}, separators=(",", ":")))
    sys.stdout.write("\n".join(out_lines) + ("\n" if out_lines else ""))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
