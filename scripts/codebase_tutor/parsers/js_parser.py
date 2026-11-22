"""JavaScript / TypeScript facts via Tree-sitter (heuristic regex fallback when unavailable)."""
from __future__ import annotations

import re
import sys

from .base import Call, Control, FileFacts, Import, Route, Symbol, body_hash, classify_outcome, short

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "del", "all", "options", "head"}
RESPOND_METHODS = {"json", "send", "render", "redirect", "sendStatus", "end", "sendFile", "download", "jsonp"}
FUNC_TYPES = {"function_expression", "function", "arrow_function", "generator_function", "generator_function_expression"}
CLASS_TYPES = {"class_declaration", "abstract_class_declaration", "class"}

_LANG_CACHE: dict = {}


def _language(lang: str):
    if lang in _LANG_CACHE:
        return _LANG_CACHE[lang]
    try:
        from tree_sitter import Language
        if lang == "javascript":
            import tree_sitter_javascript as m
            L = Language(m.language())
        else:
            import tree_sitter_typescript as m
            L = Language(m.language_tsx() if lang == "tsx" else m.language_typescript())
    except Exception:  # ImportError or ABI mismatch
        L = None
    _LANG_CACHE[lang] = L
    return L


def tree_sitter_available() -> bool:
    return _language("javascript") is not None


def _t(node) -> str:
    return node.text.decode("utf-8", "replace") if node is not None else ""


def _line(node) -> int:
    return node.start_point[0] + 1


def _end(node) -> int:
    return node.end_point[0] + 1


def _string_value(node):
    if node is None:
        return None
    if node.type == "string":
        return "".join(_t(c) for c in node.named_children if c.type in ("string_fragment", "escape_sequence"))
    if node.type == "template_string" and not any(c.type == "template_substitution" for c in node.named_children):
        return _t(node)[1:-1]
    return None


def _strip_proto(q: str) -> str:
    return q.replace(".prototype.", ".").replace(".prototype", "")


class _Walker:
    def __init__(self, path: str, lang: str, src: bytes):
        self.path, self.lang, self.src = path, lang, src
        self.f = FileFacts(parser="tree-sitter")
        self.handler_nodes: dict = {}  # node.id -> synthetic qualname
        self.route_calls: dict = {}  # node.id -> list[Route]
        self.export_aliases: set = set()
        self.named_exports: list = []  # [exported, local]
        self.export_marks: set = set()

    # ------------------------------------------------------------ helpers
    def sym(self, name, qual, kind, node, parent=None, exported=False, sig_node=None):
        sig = self._signature(sig_node or node)
        s = Symbol(name, qual, kind, _line(node), _end(node), sig, exported, parent, body_hash(_t(node)))
        self.f.symbols.append(s)
        return s

    def _signature(self, node) -> str:
        body = node.child_by_field_name("body")
        if body is not None:
            raw = self.src[node.start_byte:body.start_byte].decode("utf-8", "replace")
        else:
            raw = _t(node).split("\n")[0]
        return short(raw.strip().rstrip("{").strip(), 200)

    def control(self, node, ctx, kind, text, outcome=None):
        self.f.controls.append(Control(_line(node), ctx, kind, short(text), outcome or classify_outcome(kind, text)))

    # ------------------------------------------------------------ prepass: routes
    def prepass(self, root):
        stack = [root]
        while stack:
            n = stack.pop()
            if n.type == "call_expression":
                self._maybe_route(n)
            stack.extend(n.named_children)

    def _maybe_route(self, call):
        fn = call.child_by_field_name("function")
        args = call.child_by_field_name("arguments")
        if fn is None or fn.type != "member_expression" or args is None:
            return
        prop = _t(fn.child_by_field_name("property"))
        obj = fn.child_by_field_name("object")
        if prop not in HTTP_METHODS and prop != "use":
            return
        arglist = [a for a in args.named_children if a.type != "comment"]
        path = _string_value(arglist[0]) if arglist else None
        router = _t(obj)
        # app.route('/x').get(h) chains
        if obj is not None and obj.type == "call_expression" and path is None:
            inner_fn = obj.child_by_field_name("function")
            cur = obj
            while cur is not None and cur.type == "call_expression":
                ifn = cur.child_by_field_name("function")
                if ifn is not None and ifn.type == "member_expression" and _t(ifn.child_by_field_name("property")) == "route":
                    iargs = cur.child_by_field_name("arguments")
                    first = iargs.named_children[0] if iargs is not None and iargs.named_children else None
                    path = _string_value(first)
                    router = _t(ifn.child_by_field_name("object"))
                    break
                cur = ifn.child_by_field_name("object") if ifn is not None and ifn.type == "member_expression" else None
            if path is None:
                return
            handler_args = arglist
            del inner_fn
        elif prop == "use":
            routerish = re.search(r"(app|router|server|api|routes?)$", router, re.I) is not None
            if path is None and not routerish:
                return
            handler_args = arglist[1:] if path is not None else arglist
            if path is None:
                path = "/"
        else:
            if path is None or len(arglist) < 2:
                return  # e.g. app.get('setting') or map.get(x)
            if not path.startswith("/") and path != "*":
                return
            handler_args = arglist[1:]
        method = "USE" if prop == "use" else ("DELETE" if prop == "del" else prop.upper())
        handlers = []
        flat = []
        for a in handler_args:
            if a.type == "array":
                flat.extend(a.named_children)
            else:
                flat.append(a)
        for i, a in enumerate(flat):
            if a.type in FUNC_TYPES:
                q = f"handler:{method} {path}@{_line(a)}" + (f"#{i}" if i else "")
                self.handler_nodes[a.id] = q
                handlers.append(q)
            elif a.type in ("identifier", "member_expression", "call_expression"):
                handlers.append(short(_t(a), 100))
            # object options (fastify) are skipped
        kind = "middleware" if prop == "use" else "route"
        self.route_calls.setdefault(call.id, []).append(
            Route(_line(call), "express", method, path, handlers, short(router, 60), kind))

    # ------------------------------------------------------------ main walk
    def walk(self, node, ctx, cls=None):
        t = node.type
        handler = getattr(self, "v_" + t, None)
        if handler is not None:
            if handler(node, ctx, cls) is False:
                return
        else:
            if t in FUNC_TYPES and node.id in self.handler_nodes:
                q = self.handler_nodes[node.id]
                method_path = q.split("@")[0].replace("handler:", "")
                self.sym(f"{method_path} handler", q, "handler", node)
                self._walk_children(node, q, cls)
                return
        self._walk_children(node, ctx, cls)

    def _walk_children(self, node, ctx, cls):
        for c in node.named_children:
            self.walk(c, ctx, cls)

    # ---- declarations
    def _function_symbol(self, node, name, qual, kind, ctx, parent=None, exported=False):
        self.sym(name, qual, kind, node, parent, exported)
        self._walk_children(node, qual, None)

    def v_function_declaration(self, node, ctx, cls):
        name = _t(node.child_by_field_name("name"))
        qual = f"{ctx}.{name}" if ctx and not ctx.startswith("handler:") else name
        self._function_symbol(node, name, qual, "function", ctx, parent=ctx)
        return False

    v_generator_function_declaration = v_function_declaration

    def v_class_declaration(self, node, ctx, cls):
        name_node = node.child_by_field_name("name")
        name = _t(name_node) or "AnonymousClass"
        self.sym(name, name, "class", node, None)
        body = node.child_by_field_name("body")
        for c in node.named_children:
            if body is None or c.id != body.id:
                self.walk(c, ctx, cls)
        if body is not None:
            for m in body.named_children:
                if m.type == "method_definition":
                    mname = _t(m.child_by_field_name("name"))
                    q = f"{name}.{mname}"
                    self.sym(mname, q, "method", m, name)
                    self._walk_children(m, q, name)
                else:
                    self.walk(m, name, name)
        return False

    v_abstract_class_declaration = v_class_declaration

    def v_interface_declaration(self, node, ctx, cls):
        name = _t(node.child_by_field_name("name"))
        self.sym(name, name, "interface", node)
        return False

    def v_type_alias_declaration(self, node, ctx, cls):
        name = _t(node.child_by_field_name("name"))
        self.sym(name, name, "type", node)
        return False

    def v_enum_declaration(self, node, ctx, cls):
        name = _t(node.child_by_field_name("name"))
        self.sym(name, name, "enum", node)
        return False

    def v_variable_declarator(self, node, ctx, cls):
        name_node = node.child_by_field_name("name")
        value = node.child_by_field_name("value")
        if value is None:
            return None
        # require() imports
        req = self._require_target(value)
        if req is not None:
            module, member = req
            if name_node.type == "identifier":
                names = [[member or "default", _t(name_node)]]
            elif name_node.type == "object_pattern":
                names = []
                for p in name_node.named_children:
                    if p.type == "shorthand_property_identifier_pattern":
                        names.append([_t(p), _t(p)])
                    elif p.type == "pair_pattern":
                        names.append([_t(p.child_by_field_name("key")), _t(p.child_by_field_name("value"))])
            else:
                names = []
            self.f.imports.append(Import(_line(node), module, names, "cjs"))
            self._walk_children(value, ctx, cls)
            return False
        if name_node is None or name_node.type != "identifier":
            return None
        name = _t(name_node)
        top_level = ctx is None
        # module.exports aliasing: var app = exports = module.exports = {}
        if value.type == "assignment_expression":
            chain_target = self._export_chain(value)
            if chain_target is not None:
                self.export_aliases.add(name)
                self._handle_export_value(chain_target, ctx)
                return False
        if value.type in FUNC_TYPES and value.id not in self.handler_nodes:
            qual = name if top_level or (ctx or "").startswith("handler:") else f"{ctx}.{name}"
            self.sym(name, qual, "function", node, None if top_level else ctx, sig_node=value)
            self.f.symbols[-1].start = _line(node)
            self._walk_children(value, qual, None)
            return False
        if value.type == "class":
            self.sym(name, name, "class", node, None)
            body = value.child_by_field_name("body")
            if body is not None:
                for m in body.named_children:
                    if m.type == "method_definition":
                        mname = _t(m.child_by_field_name("name"))
                        q = f"{name}.{mname}"
                        self.sym(mname, q, "method", m, name)
                        self._walk_children(m, q, name)
            return False
        if value.type == "object" and top_level:
            self._object_members(value, name, ctx)
            return False
        return None

    def _object_members(self, obj, prefix, ctx, exported=False):
        for m in obj.named_children:
            if m.type == "method_definition":
                mname = _t(m.child_by_field_name("name"))
                q = f"{prefix}.{mname}" if prefix else mname
                self.sym(mname, q, "method" if prefix else "function", m, prefix or None, exported)
                self._walk_children(m, q, None)
            elif m.type == "pair":
                key = _t(m.child_by_field_name("key")).strip("'\"")
                val = m.child_by_field_name("value")
                if val is not None and val.type in FUNC_TYPES and val.id not in self.handler_nodes:
                    q = f"{prefix}.{key}" if prefix else key
                    self.sym(key, q, "method" if prefix else "function", m, prefix or None, exported, sig_node=val)
                    self._walk_children(val, q, None)
                elif val is not None:
                    if exported and val.type == "identifier":
                        self.named_exports.append([key, _t(val)])
                    self.walk(val, ctx, None)
            elif m.type == "shorthand_property_identifier" and exported:
                self.named_exports.append([_t(m), _t(m)])
            else:
                self.walk(m, ctx, None)

    def _require_target(self, value):
        """require('x') or require('x').y -> (module, member)."""
        member = None
        node = value
        if node.type == "member_expression":
            member = _t(node.child_by_field_name("property"))
            node = node.child_by_field_name("object")
        if node is not None and node.type == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is not None and _t(fn) == "require":
                args = node.child_by_field_name("arguments")
                first = args.named_children[0] if args is not None and args.named_children else None
                mod = _string_value(first)
                if mod is not None:
                    return mod, member
        return None

    def _export_chain(self, assign):
        """For a = b = module.exports = X, return X if chain includes module.exports/exports."""
        cur, hit = assign, False
        while cur is not None and cur.type == "assignment_expression":
            left = _t(cur.child_by_field_name("left"))
            if left in ("module.exports", "exports"):
                hit = True
            cur = cur.child_by_field_name("right")
        return cur if hit else None

    def _handle_export_value(self, value, ctx):
        if value.type == "identifier":
            self.named_exports.append(["default", _t(value)])
            self.export_aliases.add(_t(value))
        elif value.type == "object":
            self._object_members(value, "", ctx, exported=True)
        elif value.type in FUNC_TYPES:
            nm = _t(value.child_by_field_name("name")) or "default"
            self.sym(nm, nm, "function", value, None, True)
            self.named_exports.append(["default", nm])
            self._walk_children(value, nm, None)
        elif value.type == "class":
            nm = _t(value.child_by_field_name("name")) or "default"
            self.sym(nm, nm, "class", value, None, True)
            self.named_exports.append(["default", nm])
            self._walk_children(value, nm, nm)
        else:
            self.walk(value, ctx, None)

    def v_assignment_expression(self, node, ctx, cls):
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is None or right is None:
            return None
        ltxt = _t(left)
        if ltxt in ("module.exports", "exports"):
            chain_target = self._export_chain(node)
            self._handle_export_value(chain_target if chain_target is not None else right, ctx)
            return False
        if left.type == "member_expression":
            prop = _t(left.child_by_field_name("property"))
            obj = _t(left.child_by_field_name("object"))
            if obj in ("module.exports", "exports"):
                if right.type in FUNC_TYPES and right.id not in self.handler_nodes:
                    self.sym(prop, prop, "function", node, None, True, sig_node=right)
                    self._walk_children(right, prop, None)
                    return False
                if right.type == "identifier":
                    self.named_exports.append([prop, _t(right)])
                req = self._require_target(right)
                if req is not None:
                    self.f.imports.append(Import(_line(node), req[0], [[req[1] or "default", prop]], "cjs", True))
                    self.named_exports.append([prop, prop])
                return None
            if right.type in FUNC_TYPES and right.id not in self.handler_nodes and ctx is None:
                qual = _strip_proto(ltxt)
                parent = qual.rsplit(".", 1)[0]
                self.sym(prop, qual, "method", node, parent, sig_node=right)
                self._walk_children(right, qual, parent)
                return False
        return None

    # ---- ESM
    def v_import_statement(self, node, ctx, cls):
        src = _string_value(node.child_by_field_name("source"))
        if src is None:
            return False
        names = []
        for c in node.named_children:
            if c.type == "import_clause":
                for cc in c.named_children:
                    if cc.type == "identifier":
                        names.append(["default", _t(cc)])
                    elif cc.type == "namespace_import":
                        ids = [x for x in cc.named_children if x.type == "identifier"]
                        if ids:
                            names.append(["*", _t(ids[-1])])
                    elif cc.type == "named_imports":
                        for spec in cc.named_children:
                            if spec.type == "import_specifier":
                                nm = spec.child_by_field_name("name")
                                al = spec.child_by_field_name("alias")
                                names.append([_t(nm), _t(al) if al is not None else _t(nm)])
        self.f.imports.append(Import(_line(node), src, names, "esm"))
        return False

    def v_export_statement(self, node, ctx, cls):
        src = _string_value(node.child_by_field_name("source"))
        decl = node.child_by_field_name("declaration")
        is_default = any(not c.is_named and _t(c) == "default" for c in node.children)
        if src is not None:
            names = []
            for c in node.named_children:
                if c.type == "export_clause":
                    for spec in c.named_children:
                        nm = spec.child_by_field_name("name")
                        al = spec.child_by_field_name("alias")
                        names.append([_t(nm), _t(al) if al is not None else _t(nm)])
                        self.named_exports.append([_t(al) if al is not None else _t(nm), _t(nm)])
            if not names:
                names = [["*", "*"]]
            self.f.imports.append(Import(_line(node), src, names, "esm", True))
            return False
        if decl is not None:
            before = len(self.f.symbols)
            self.walk(decl, ctx, cls)
            for s in self.f.symbols[before:]:
                if s.parent is None:
                    s.exported = True
                    self.named_exports.append(["default" if is_default else s.name, s.qualname])
            if decl.type in ("lexical_declaration", "variable_declaration"):
                for d in decl.named_children:
                    if d.type == "variable_declarator":
                        nm = _t(d.child_by_field_name("name"))
                        self.export_marks.add(nm)
            return False
        for c in node.named_children:
            if c.type == "export_clause":
                for spec in c.named_children:
                    nm = spec.child_by_field_name("name")
                    al = spec.child_by_field_name("alias")
                    self.named_exports.append([_t(al) if al is not None else _t(nm), _t(nm)])
            elif is_default:
                if c.type == "identifier":
                    self.named_exports.append(["default", _t(c)])
                elif c.type in FUNC_TYPES or c.type in CLASS_TYPES:
                    nm = _t(c.child_by_field_name("name")) or "default"
                    kind = "class" if c.type in CLASS_TYPES else "function"
                    self.sym(nm, nm, kind, c, None, True)
                    self.named_exports.append(["default", nm])
                    self._walk_children(c, nm, nm if kind == "class" else None)
                else:
                    self.walk(c, ctx, cls)
        return False

    # ---- calls, env, control
    def v_call_expression(self, node, ctx, cls):
        fn = node.child_by_field_name("function")
        args = node.child_by_field_name("arguments")
        if fn is not None:
            if fn.type == "import":  # dynamic import()
                first = args.named_children[0] if args is not None and args.named_children else None
                mod = _string_value(first)
                if mod:
                    self.f.imports.append(Import(_line(node), mod, [["*", "*"]], "dynamic"))
            elif _t(fn) == "require":
                first = args.named_children[0] if args is not None and args.named_children else None
                mod = _string_value(first)
                if mod and not (node.parent is not None and node.parent.type in ("variable_declarator", "member_expression")):
                    self.f.imports.append(Import(_line(node), mod, [], "cjs"))
            else:
                expr = short(_t(fn), 120)
                if fn.type == "member_expression":
                    name = _t(fn.child_by_field_name("property"))
                    root = fn
                    while root.type in ("member_expression", "call_expression", "subscript_expression", "parenthesized_expression"):
                        nxt = root.child_by_field_name("object") if root.type != "call_expression" else root.child_by_field_name("function")
                        if nxt is None:
                            break
                        root = nxt
                    recv = _t(root)[:40] if root.type in ("identifier", "this", "super") else short(_t(fn.child_by_field_name("object")), 40)
                else:
                    name, recv = expr.split("(")[0].split(".")[-1], None
                self.f.calls.append(Call(_line(node), ctx, expr, name, recv))
                full = short(_t(node), 160)
                if name in RESPOND_METHODS and recv in ("res", "response", "reply", "ctx", "h"):
                    is_inner = node.parent is not None and node.parent.type == "member_expression"
                    if not is_inner:
                        self.control(node, ctx, "respond", full)
                if fn.type == "identifier" and name == "next":
                    has_args = args is not None and len(args.named_children) > 0
                    if has_args:
                        self.control(node, ctx, "next-error", full, "failure")
                    else:
                        self.control(node, ctx, "next", full, "neutral")
                if name == "listen" and recv and re.search(r"(app|server|fastify)", recv, re.I):
                    self.f.entry_reasons.append(f"{expr}() starts a server (line {_line(node)})")
        if node.id in self.route_calls:
            self.f.routes.extend(self.route_calls[node.id])
        return None

    def v_new_expression(self, node, ctx, cls):
        ctor = node.child_by_field_name("constructor")
        if ctor is not None:
            expr = "new " + short(_t(ctor), 100)
            name = _t(ctor).split(".")[-1]
            recv = _t(ctor).split(".")[0] if "." in _t(ctor) else None
            self.f.calls.append(Call(_line(node), ctx, expr, name, recv))
        return None

    def v_member_expression(self, node, ctx, cls):
        obj = node.child_by_field_name("object")
        if obj is not None and _t(obj) in ("process.env", "import.meta.env"):
            self.f.env_vars.append([_line(node), _t(node.child_by_field_name("property"))])
        return None

    def v_subscript_expression(self, node, ctx, cls):
        obj = node.child_by_field_name("object")
        idx = node.child_by_field_name("index")
        if obj is not None and _t(obj) == "process.env":
            val = _string_value(idx)
            if val:
                self.f.env_vars.append([_line(node), val])
        return None

    def v_if_statement(self, node, ctx, cls):
        if ctx is not None:
            cond = node.child_by_field_name("condition")
            self.control(node, ctx, "if", "if " + _t(cond))
            alt = node.child_by_field_name("alternative")
            if alt is not None and not any(c.type == "if_statement" for c in alt.named_children):
                self.control(alt, ctx, "else", "else (of if " + short(_t(cond), 80) + ")", "neutral")
        return None

    def v_return_statement(self, node, ctx, cls):
        if ctx is not None:
            self.control(node, ctx, "return", _t(node).rstrip(";"))
        return None

    def v_throw_statement(self, node, ctx, cls):
        if ctx is not None:
            self.control(node, ctx, "throw", _t(node).rstrip(";"), "failure")
        return None

    def v_try_statement(self, node, ctx, cls):
        if ctx is not None:
            self.control(node, ctx, "try", "try", "neutral")
        return None

    def v_catch_clause(self, node, ctx, cls):
        if ctx is not None:
            param = node.child_by_field_name("parameter")
            self.control(node, ctx, "catch", "catch (" + _t(param) + ")", "failure")
        return None

    # ------------------------------------------------------------ finalize
    def finalize(self, text: str):
        by_qual = {s.qualname: s for s in self.f.symbols}
        for s in self.f.symbols:
            root = s.qualname.split(".")[0]
            if s.parent and root in self.export_aliases and s.qualname.count(".") == 1:
                s.exported = True
                self.named_exports.append([s.name, s.qualname])
            if s.name in self.export_marks and s.parent is None:
                s.exported = True
        for exported, local in self.named_exports:
            if local in by_qual:
                by_qual[local].exported = True
        seen = set()
        for e in self.named_exports:
            key = (e[0], e[1])
            if key not in seen:
                seen.add(key)
                self.f.exports.append([e[0], e[1]])
        imported_mods = {i.module for i in self.f.imports}
        fw = "express"
        if imported_mods & {"koa-router", "@koa/router", "koa"}:
            fw = "koa"
        elif "fastify" in imported_mods:
            fw = "fastify"
        elif "hono" in imported_mods:
            fw = "hono"
        for r in self.f.routes:
            r.framework = fw
        if text.startswith("#!") and "node" in text.split("\n", 1)[0]:
            self.f.entry_reasons.append("node shebang (line 1)")


def parse_js(path: str, lang: str, text: str) -> FileFacts:
    L = _language(lang)
    if L is None:
        return _heuristic(path, text)
    from tree_sitter import Parser
    src = text.encode("utf-8")
    tree = Parser(L).parse(src)
    w = _Walker(path, lang, src)
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old, 20000))
    try:
        w.prepass(tree.root_node)
        w.walk(tree.root_node, None)
    except RecursionError:
        w.f.errors.append("nesting too deep; partial facts")
    finally:
        sys.setrecursionlimit(old)
    if tree.root_node.has_error:
        w.f.errors.append("syntax errors present; facts may be partial")
    w.finalize(text)
    return w.f


# ---------------------------------------------------------------- heuristic fallback
_RE_FUNC = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\*?\s+([A-Za-z_$][\w$]*)\s*\(", re.M)
_RE_ASSIGN_FN = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)", re.M)
_RE_CLASS = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)", re.M)
_RE_REQUIRE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")
_RE_IMPORT = re.compile(r"""^\s*import\s+(?:[^'"]*?from\s+)?['"]([^'"]+)['"]""", re.M)
_RE_ROUTE = re.compile(r"""\b([A-Za-z_$][\w$]*)\.(get|post|put|patch|delete|all|use)\(\s*['"`](/[^'"`]*)['"`]""")


def _heuristic(path: str, text: str) -> FileFacts:
    f = FileFacts(parser="heuristic")
    lines = text.splitlines()

    def line_of(pos):
        return text.count("\n", 0, pos) + 1

    for rx, kind in ((_RE_FUNC, "function"), (_RE_ASSIGN_FN, "function"), (_RE_CLASS, "class")):
        for m in rx.finditer(text):
            ln = line_of(m.start(1))
            f.symbols.append(Symbol(m.group(1), m.group(1), kind, ln, ln, short(lines[ln - 1].strip(), 200),
                                    "export" in lines[ln - 1], None, ""))
    for m in _RE_REQUIRE.finditer(text):
        f.imports.append(Import(line_of(m.start()), m.group(1), [], "cjs"))
    for m in _RE_IMPORT.finditer(text):
        f.imports.append(Import(line_of(m.start()), m.group(1), [], "esm"))
    for m in _RE_ROUTE.finditer(text):
        method = "USE" if m.group(2) == "use" else m.group(2).upper()
        f.routes.append(Route(line_of(m.start()), "express", method, m.group(3), [], m.group(1),
                              "middleware" if method == "USE" else "route"))
    f.errors.append("tree-sitter unavailable: heuristic extraction (no calls/control flow; end lines unknown)")
    return f
