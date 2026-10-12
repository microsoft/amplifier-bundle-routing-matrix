"""Closed interval-union grammar; host operations only parse, validate and hash.

This is not an arbitrary-Python sandbox. Resource containment and qualification
are caller-owned. The only model compile/exec sites are TEXT in ASSESSOR_DRIVER,
which must be staged and run exclusively in the separately qualified container.
No live_smoke import, model import, host execution entry point or shared mutable
builtin mapping is provided.
"""

import ast
import hashlib
import math
import json
from dataclasses import dataclass
from pathlib import Path

GRAMMAR_VERSION = "restricted-python-v1"
MAX_SOURCE_BYTES = 16 * 1024
MAX_AST_NODES = 2000
MAX_AST_DEPTH = 40  # Module is depth 1; operators/contexts/annotations count.
MAX_FUNCTIONS = 8
MAX_DOCSTRING_CHARS = 1024
# Literal bounds derive from the source envelope, not an endpoint value policy.
MAX_STRING_CHARS = MAX_SOURCE_BYTES
MAX_INTEGER_BITS = MAX_SOURCE_BYTES * 8
MAX_PROTOCOL_BYTES = 65536
MAX_CASES = 256
MAX_INPUT_NODES = 4096
MAX_INPUT_DEPTH = 16
CASE_GROUPS = frozenset({"union", "touching_empty", "invalid", "immutability"})
SAFE_BUILTIN_NAMES = (
    "len",
    "type",
    "isinstance",
    "int",
    "bool",
    "list",
    "tuple",
    "range",
    "sorted",
    "enumerate",
    "zip",
    "reversed",
    "min",
    "max",
    "sum",
    "abs",
    "all",
    "any",
    "ValueError",
)
_METHOD_NAMES = frozenset({"append", "extend", "sort", "copy", "pop"})
_ANNOTATION_NAMES = frozenset({"int", "bool", "list", "tuple"})
_ALLOWED_NODE_TYPES = frozenset(
    {
        ast.Module,
        ast.FunctionDef,
        ast.arguments,
        ast.arg,
        ast.Return,
        ast.Assign,
        ast.AnnAssign,
        ast.AugAssign,
        ast.Expr,
        ast.If,
        ast.For,
        ast.While,
        ast.Break,
        ast.Continue,
        ast.Pass,
        ast.Raise,
        ast.Name,
        ast.Constant,
        ast.List,
        ast.Tuple,
        ast.BoolOp,
        ast.BinOp,
        ast.UnaryOp,
        ast.Compare,
        ast.IfExp,
        ast.Subscript,
        ast.Slice,
        ast.Call,
        ast.Attribute,
        ast.keyword,
        ast.ListComp,
        ast.GeneratorExp,
        ast.comprehension,
        ast.And,
        ast.Or,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.FloorDiv,
        ast.Mod,
        ast.Not,
        ast.UAdd,
        ast.USub,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.In,
        ast.NotIn,
        ast.Is,
        ast.IsNot,
        ast.Load,
        ast.Store,
    }
)


@dataclass(frozen=True)
class RestrictedAdmission:
    version: str
    source_sha256: str
    normalized_sha256: str
    function_names: tuple[str, ...]


class ArtifactUngradable(ValueError):
    """Sanitized static reason only; never include artifact text or traceback."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ArtifactUngradable(reason)


def _public_name(name: str) -> None:
    _require(
        name.isidentifier() and not name.startswith("_") and "__" not in name,
        "restricted_name",
    )


def _bounded_tree(tree: ast.Module) -> tuple[ast.FunctionDef, ...]:
    """Iterative pre-normalization closed-node, size and depth check."""
    stack = [(tree, 1)]
    functions = []
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        _require(count <= MAX_AST_NODES, "restricted_ast_nodes")
        _require(depth <= MAX_AST_DEPTH, "restricted_ast_depth")
        _require(type(node) in _ALLOWED_NODE_TYPES, "restricted_ast_node")
        if isinstance(node, ast.FunctionDef):
            functions.append(node)
            _require(len(functions) <= MAX_FUNCTIONS, "restricted_functions")
        stack.extend(
            (child, depth + 1) for child in reversed(list(ast.iter_child_nodes(node)))
        )
    return tuple(functions)


def _docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and type(statement.value.value) is str
    )


@dataclass
class _Scope:
    bound: set[str]
    parent: "_Scope | None"

    def contains(self, name: str) -> bool:
        return name in self.bound or (
            self.parent is not None and self.parent.contains(name)
        )


class _Validator:
    def __init__(self, functions: tuple[ast.FunctionDef, ...]):
        names = tuple(function.name for function in functions)
        for name in names:
            _public_name(name)
        _require(len(set(names)) == len(names), "restricted_function_duplicate")
        _require(
            not (set(names) & set(SAFE_BUILTIN_NAMES)),
            "restricted_function_builtin",
        )
        self.function_names = names
        self.helpers = frozenset(names) - {"coalesce"}
        self.protected = frozenset(SAFE_BUILTIN_NAMES) | frozenset(names)

    def binding(self, name: str) -> None:
        _public_name(name)
        _require(name not in self.protected, "restricted_binding")

    def load(self, name: str, scope: _Scope) -> None:
        _public_name(name)
        _require(
            name in SAFE_BUILTIN_NAMES or scope.contains(name),
            "restricted_unbound_name",
        )

    def annotation(self, node: ast.expr | None, *, tuple_allowed: bool = False) -> None:
        if node is None:
            return
        if isinstance(node, ast.Name):
            _require(
                isinstance(node.ctx, ast.Load) and node.id in _ANNOTATION_NAMES,
                "restricted_annotation",
            )
        elif isinstance(node, ast.Constant):
            _require(node.value is None, "restricted_annotation")
        elif isinstance(node, ast.Subscript):
            _require(
                isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Name)
                and isinstance(node.value.ctx, ast.Load)
                and node.value.id in {"list", "tuple"},
                "restricted_annotation",
            )
            self.annotation(node.slice, tuple_allowed=True)
        elif isinstance(node, ast.Tuple) and tuple_allowed:
            _require(isinstance(node.ctx, ast.Load), "restricted_annotation")
            for element in node.elts:
                self.annotation(element, tuple_allowed=True)
        else:
            raise ArtifactUngradable("restricted_annotation")

    def function(self, node: ast.FunctionDef, parent: _Scope) -> None:
        args = node.args
        _require(
            not node.decorator_list
            and not args.defaults
            and not args.kwonlyargs
            and not args.kw_defaults
            and args.vararg is None
            and args.kwarg is None
            and not getattr(node, "type_params", ())
            and node.type_comment is None,
            "restricted_function_signature",
        )
        positional = args.posonlyargs + args.args
        parameters = [arg.arg for arg in positional]
        _require(
            len(set(parameters)) == len(parameters), "restricted_parameter_duplicate"
        )
        if node.name == "coalesce":
            _require(parameters == ["ranges"], "restricted_coalesce_signature")
        for arg in positional:
            self.binding(arg.arg)
            _require(arg.type_comment is None, "restricted_type_comment")
            self.annotation(arg.annotation)
        self.annotation(node.returns)

        # Python function locals are determined over the entire function body.
        # Nested definitions bind their name HERE, but their bodies and
        # comprehension targets have distinct scopes.
        bound = set(parameters)
        stack = list(node.body)
        while stack:
            child = stack.pop()
            if isinstance(child, ast.FunctionDef):
                bound.add(child.name)
            elif isinstance(child, (ast.ListComp, ast.GeneratorExp)):
                continue
            else:
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    self.binding(child.id)
                    bound.add(child.id)
                stack.extend(ast.iter_child_nodes(child))
        self.block(node.body, _Scope(bound, parent), 0, allow_docstring=True)

    def target(self, node: ast.expr, scope: _Scope) -> None:
        _require(isinstance(getattr(node, "ctx", None), ast.Store), "restricted_target")
        if isinstance(node, ast.Name):
            self.binding(node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for element in node.elts:
                self.target(element, scope)
        elif isinstance(node, ast.Subscript):
            self.expression(node.value, scope)
            self.expression(node.slice, scope)
        else:
            raise ArtifactUngradable("restricted_target")

    def block(
        self,
        body: list[ast.stmt],
        scope: _Scope,
        loop_depth: int,
        *,
        allow_docstring: bool = False,
    ) -> None:
        for index, node in enumerate(body):
            if _docstring(node):
                _require(allow_docstring and index == 0, "restricted_expr_statement")
                _require(
                    len(node.value.value) <= MAX_DOCSTRING_CHARS,
                    "restricted_docstring",
                )
                continue
            self.statement(node, scope, loop_depth)

    def statement(self, node: ast.stmt, scope: _Scope, loop_depth: int) -> None:
        if isinstance(node, ast.FunctionDef):
            self.function(node, scope)
        elif isinstance(node, ast.Return):
            if node.value is not None:
                self.expression(node.value, scope)
        elif isinstance(node, ast.Assign):
            _require(node.type_comment is None, "restricted_type_comment")
            for target in node.targets:
                self.target(target, scope)
            self.expression(node.value, scope)
        elif isinstance(node, ast.AnnAssign):
            _require(node.value is not None, "restricted_annotation_no_value")
            self.annotation(node.annotation)
            self.target(node.target, scope)
            self.expression(node.value, scope)
        elif isinstance(node, ast.AugAssign):
            self.target(node.target, scope)
            self.expression(node.value, scope)
        elif isinstance(node, ast.Expr):
            _require(isinstance(node.value, ast.Call), "restricted_expr_statement")
            self.call(node.value, scope)
        elif isinstance(node, ast.If):
            self.expression(node.test, scope)
            self.block(node.body, scope, loop_depth)
            self.block(node.orelse, scope, loop_depth)
        elif isinstance(node, (ast.For, ast.While)):
            if isinstance(node, ast.For):
                _require(node.type_comment is None, "restricted_type_comment")
                self.target(node.target, scope)
                self.expression(node.iter, scope)
            else:
                self.expression(node.test, scope)
            self.block(node.body, scope, loop_depth + 1)
            self.block(node.orelse, scope, loop_depth)
        elif isinstance(node, (ast.Break, ast.Continue)):
            _require(loop_depth > 0, "restricted_loop_control")
        elif isinstance(node, ast.Pass):
            pass
        elif isinstance(node, ast.Raise):
            _require(
                node.cause is None
                and isinstance(node.exc, ast.Call)
                and isinstance(node.exc.func, ast.Name)
                and node.exc.func.id == "ValueError",
                "restricted_raise",
            )
            self.call(node.exc, scope)
        else:
            raise ArtifactUngradable("restricted_statement")

    def call(self, node: ast.Call, scope: _Scope) -> None:
        if isinstance(node.func, ast.Name):
            name = node.func.id
            self.expression(node.func, scope)
            _require(
                name in SAFE_BUILTIN_NAMES or name in self.function_names,
                "restricted_call_target",
            )
            if name == "type":
                _require(
                    len(node.args) == 1 and not node.keywords,
                    "restricted_type_arity",
                )
            if name == "ValueError":
                _require(
                    not node.keywords
                    and (
                        not node.args
                        or (
                            len(node.args) == 1
                            and isinstance(node.args[0], ast.Constant)
                            and type(node.args[0].value) is str
                            and len(node.args[0].value) <= MAX_STRING_CHARS
                        )
                    ),
                    "restricted_value_error",
                )
            keyword_names = (
                {"key", "reverse"}
                if name == "sorted"
                else {"start"}
                if name == "enumerate"
                else set()
            )
        elif isinstance(node.func, ast.Attribute):
            _require(
                isinstance(node.func.ctx, ast.Load) and node.func.attr in _METHOD_NAMES,
                "restricted_method",
            )
            self.expression(node.func.value, scope)
            keyword_names = {"key", "reverse"} if node.func.attr == "sort" else set()
        else:
            raise ArtifactUngradable("restricted_call_target")
        seen = set()
        for keyword in node.keywords:
            _require(
                keyword.arg in keyword_names and keyword.arg not in seen,
                "restricted_keyword",
            )
            seen.add(keyword.arg)
            if keyword.arg == "key":
                _require(
                    isinstance(keyword.value, ast.Name)
                    and keyword.value.id in self.helpers,
                    "restricted_sort_key",
                )
            elif keyword.arg == "reverse":
                # Finite keyword grammar: a literal bool, not truthiness/coercion.
                _require(
                    isinstance(keyword.value, ast.Constant)
                    and type(keyword.value.value) is bool,
                    "restricted_sort_reverse",
                )
            self.expression(keyword.value, scope)
        for arg in node.args:
            self.expression(arg, scope)

    def comprehension(
        self, node: ast.ListComp | ast.GeneratorExp, scope: _Scope
    ) -> None:
        _require(bool(node.generators), "restricted_comprehension")
        bound = set()
        for generator in node.generators:
            _require(generator.is_async == 0, "restricted_comprehension_async")
            for child in ast.walk(generator.target):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    bound.add(child.id)
        inner = _Scope(bound, scope)
        for index, generator in enumerate(node.generators):
            # The leftmost iterable runs in the enclosing scope. All other
            # iterables/filters/result run in the comprehension's lexical scope.
            self.expression(generator.iter, scope if index == 0 else inner)
            self.target(generator.target, inner)
            for condition in generator.ifs:
                self.expression(condition, inner)
        self.expression(node.elt, inner)

    def expression(self, node: ast.expr, scope: _Scope) -> None:
        if isinstance(node, ast.Name):
            _require(isinstance(node.ctx, ast.Load), "restricted_context")
            self.load(node.id, scope)
        elif isinstance(node, ast.Constant):
            value = node.value
            _require(
                value is None or type(value) in {bool, int, float, str},
                "restricted_constant",
            )
            if type(value) is float:
                _require(math.isfinite(value), "restricted_constant")
            elif type(value) is int:
                _require(value.bit_length() <= MAX_INTEGER_BITS, "restricted_constant")
            elif type(value) is str:
                _require(len(value) <= MAX_STRING_CHARS, "restricted_constant")
        elif isinstance(node, (ast.List, ast.Tuple)):
            _require(isinstance(node.ctx, ast.Load), "restricted_context")
            for element in node.elts:
                self.expression(element, scope)
        elif isinstance(node, ast.BoolOp):
            for value in node.values:
                self.expression(value, scope)
        elif isinstance(node, ast.BinOp):
            self.expression(node.left, scope)
            self.expression(node.right, scope)
        elif isinstance(node, ast.UnaryOp):
            self.expression(node.operand, scope)
        elif isinstance(node, ast.Compare):
            self.expression(node.left, scope)
            for comparator in node.comparators:
                self.expression(comparator, scope)
        elif isinstance(node, ast.IfExp):
            for value in (node.test, node.body, node.orelse):
                self.expression(value, scope)
        elif isinstance(node, ast.Subscript):
            _require(isinstance(node.ctx, ast.Load), "restricted_context")
            self.expression(node.value, scope)
            self.expression(node.slice, scope)
        elif isinstance(node, ast.Slice):
            for value in (node.lower, node.upper, node.step):
                if value is not None:
                    self.expression(value, scope)
        elif isinstance(node, ast.Call):
            self.call(node, scope)
        elif isinstance(node, (ast.ListComp, ast.GeneratorExp)):
            self.comprehension(node, scope)
        else:
            # In particular: Attribute is valid ONLY as a direct Call.func.
            raise ArtifactUngradable("restricted_expression")


class _StripAnnotations(ast.NodeTransformer):
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        node.returns = None
        for arg in node.args.posonlyargs + node.args.args:
            arg.annotation = None
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.Assign:
        return ast.copy_location(
            ast.Assign(targets=[node.target], value=node.value), node
        )


def normalized_digest(tree: ast.Module) -> str:
    """Location-free explicit normalized tree; stable across qualified Python minors.

    ast.dump changed empty-field rendering in Python 3.13. Empty/None optional
    fields carry no execution semantics in this closed grammar.
    """

    def project(value):
        if isinstance(value, ast.AST):
            return {
                "node": type(value).__name__,
                "fields": {
                    k: project(v)
                    for k, v in ast.iter_fields(value)
                    if v is not None and v != []
                },
            }
        if isinstance(value, list):
            return [project(v) for v in value]
        if type(value) is int:
            return {"integer_hex": hex(value)}
        return value

    return hashlib.sha256(
        json.dumps(
            project(tree),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def validate_interval_module(source: str) -> tuple[ast.Module, RestrictedAdmission]:
    """Parse/validate/strip annotations; NEVER compile or execute the artifact.

    normalized_sha256 hashes the explicit normalized tree projection, no locations.
    Host/container must use the qualified Python/validator version, and the
    container independently reconstructs this AST from immutable source bytes.
    """
    _require(type(source) is str, "restricted_source_type")
    _require(len(source) <= MAX_SOURCE_BYTES, "restricted_source_bytes")
    try:
        raw = source.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ArtifactUngradable("restricted_source_encoding") from None
    _require(len(raw) <= MAX_SOURCE_BYTES, "restricted_source_bytes")
    try:
        tree = ast.parse(source, mode="exec", type_comments=True)
    except (SyntaxError, ValueError, RecursionError):
        raise ArtifactUngradable("restricted_source_parse") from None
    functions = _bounded_tree(tree)
    _require(not tree.type_ignores, "restricted_type_comment")
    body = tree.body
    if body and _docstring(body[0]):
        _require(
            len(body[0].value.value) <= MAX_DOCSTRING_CHARS, "restricted_docstring"
        )
        body = body[1:]
    _require(
        len(body) == 1
        and isinstance(body[0], ast.FunctionDef)
        and body[0].name == "coalesce",
        "restricted_module",
    )
    validator = _Validator(functions)
    validator.function(body[0], _Scope({"coalesce"}, None))
    normalized = ast.fix_missing_locations(_StripAnnotations().visit(tree))
    digest = normalized_digest(normalized)
    return normalized, RestrictedAdmission(
        GRAMMAR_VERSION,
        hashlib.sha256(raw).hexdigest(),
        digest,
        validator.function_names,
    )


def _copy_input(value: object, depth: int, remaining: list[int]) -> object:
    remaining[0] -= 1
    _require(remaining[0] >= 0 and depth <= MAX_INPUT_DEPTH, "assessor_input_bound")
    kind = type(value)
    if value is None or kind is bool:
        return value
    if kind is int:
        _require(value.bit_length() <= MAX_INTEGER_BITS, "assessor_input_bound")
        return value
    if kind is float:
        _require(math.isfinite(value), "assessor_input_primitive")
        return value
    if kind is str:
        _require(len(value) <= MAX_STRING_CHARS, "assessor_input_bound")
        return value
    if kind is list:
        _require(len(value) <= remaining[0], "assessor_input_bound")
        return [_copy_input(child, depth + 1, remaining) for child in value]
    if kind is dict:
        _require(len(value) <= remaining[0], "assessor_input_bound")
        _require(
            all(type(key) is str and len(key) <= MAX_STRING_CHARS for key in value),
            "assessor_input_primitive",
        )
        return {
            key: _copy_input(child, depth + 1, remaining)
            for key, child in value.items()
        }
    raise ArtifactUngradable("assessor_input_primitive")


def validate_assessment_cases(cases: object) -> list[dict]:
    """Bounded trusted protocol input; reject answer keys/unknown fields.

    Returns a fresh JSON-primitive copy. This is protocol validation, not a
    functional grade, and permits intentionally malformed interval inputs.
    Complete four-group coverage is required; expected union answers stay in
    the controller and must NEVER be included in this input.
    """
    _require(type(cases) is list and 0 < len(cases) <= MAX_CASES, "assessor_cases")
    required = {"id", "group", "input", "invalid"}
    optional = {"pairs_tuple", "outer_tuple"}
    identifiers = set()
    groups = set()
    result = []
    remaining = [MAX_INPUT_NODES]
    for case in cases:
        _require(
            type(case) is dict
            and all(type(key) is str for key in case)
            and required <= set(case) <= required | optional,
            "assessor_case_fields",
        )
        identifier = case["id"]
        group = case["group"]
        _require(
            type(identifier) is str
            and 0 < len(identifier) <= 64
            and identifier not in identifiers,
            "assessor_case_id",
        )
        _require(type(group) is str and group in CASE_GROUPS, "assessor_case_group")
        _require(type(case["invalid"]) is bool, "assessor_case_flag")
        for flag in optional & set(case):
            _require(type(case[flag]) is bool, "assessor_case_flag")
        value = _copy_input(case["input"], 1, remaining)
        if case.get("pairs_tuple"):
            _require(
                type(value) is list and all(type(pair) is list for pair in value),
                "assessor_tuple_conversion",
            )
        if case.get("outer_tuple"):
            _require(type(value) is list, "assessor_tuple_conversion")
        result.append({**case, "input": value})
        identifiers.add(identifier)
        groups.add(group)
    _require(groups == CASE_GROUPS, "assessor_case_groups")
    return result


def primitive_input_unchanged(value: object, before: object) -> bool:
    """Compare exact primitive structures without invoking artifact protocols.

    Nonprimitives, cycles, growth beyond the input envelope and type changes
    count as mutation. Tuple-converted inputs are supported. In particular
    bool/int equality cannot conceal a change; no repr/deepcopy of mutated data.
    """
    stack = [(value, before, 1)]
    remaining = MAX_INPUT_NODES
    while stack:
        current, original, depth = stack.pop()
        remaining -= 1
        if remaining < 0 or depth > MAX_INPUT_DEPTH:
            return False
        kind = type(current)
        if kind is not type(original):
            return False
        if current is None or kind in {bool, int, float, str}:
            if current != original:
                return False
        elif kind in {list, tuple}:
            if len(current) != len(original) or len(current) > remaining:
                return False
            stack.extend(
                (child, old, depth + 1) for child, old in zip(current, original)
            )
        elif kind is dict:
            if (
                len(current) != len(original)
                or len(current) > remaining
                or not all(type(key) is str for key in current)
                or set(current) != set(original)
            ):
                return False
            stack.extend((current[key], original[key], depth + 1) for key in original)
        else:
            return False
    return True


def normalize_interval_answer(answer: object) -> tuple[bool, list | None]:
    """Exact shape gate followed by a fresh, driver-owned primitive copy."""
    if type(answer) is not list:
        return False, None
    _require(len(answer) <= MAX_PROTOCOL_BYTES, "assessor_output_bound")
    result = []
    for pair in answer:
        if (
            type(pair) is not tuple
            or len(pair) != 2
            or type(pair[0]) is not int
            or type(pair[1]) is not int
        ):
            return False, None
        _require(
            all(value.bit_length() <= MAX_INTEGER_BITS for value in pair),
            "assessor_output_bound",
        )
        result.append([pair[0], pair[1]])
    return True, result


# This is trusted container source, NOT a host execution function.
# Stage /input/{driver.py,restricted_interval.py,solution.py} read-only; invoke:
# python -I -B /input/driver.py SOURCE_SHA256 NORMALIZED_SHA256 GRAMMAR_SHA256
# stdin remains the existing cases array. The grammar SHA binds the exact
# validator+driver-source file bytes; separately pin the staged driver bytes.
ASSESSOR_DRIVER = r"""
import builtins
import copy
import json
import sys
from pathlib import Path
stage = "imports"

sys.path.insert(0, "/input")
from restricted_interval import (
    GRAMMAR_SHA256, GRAMMAR_VERSION, MAX_SOURCE_BYTES, MAX_PROTOCOL_BYTES,
    SAFE_BUILTIN_NAMES, normalize_interval_answer, primitive_input_unchanged,
    validate_assessment_cases, validate_interval_module,
)


def require(condition):
    if not condition:
        raise ValueError("assessor_protocol")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("assessor_protocol")


def main():
    global stage
    require(len(sys.argv) == 4)
    locks = sys.argv[1:]
    require(all(len(lock) == 64 and
                all(char in "0123456789abcdef" for char in lock)
                for lock in locks))
    require(locks[2] == GRAMMAR_SHA256)
    stage = "source"
    with Path("/input/solution.py").open("rb") as stream:
        raw_source = stream.read(MAX_SOURCE_BYTES + 1)
    require(len(raw_source) <= MAX_SOURCE_BYTES)
    normalized, admission = validate_interval_module(
        raw_source.decode("utf-8", errors="strict")
    )
    require(admission.version == GRAMMAR_VERSION)
    stage = "hashes"
    require(admission.source_sha256 == locks[0])
    require(admission.normalized_sha256 == locks[1])

    raw_cases = sys.stdin.buffer.read(MAX_PROTOCOL_BYTES + 1)
    stage = "cases"
    require(len(raw_cases) <= MAX_PROTOCOL_BYTES)
    cases = validate_assessment_cases(json.loads(
        raw_cases.decode("utf-8", errors="strict"),
        object_pairs_hook=unique_object, parse_constant=reject_constant,
    ))

    # Fresh references/mapping and a distinct namespace; no driver globals,
    # validator helpers, modules, cases or records are reachable from the model.
    model_ns = {"__builtins__": {
        name: getattr(builtins, name) for name in SAFE_BUILTIN_NAMES
    }}
    stage = "compile"
    exec(compile(normalized, "<restricted-interval>", "exec",
                 dont_inherit=True, optimize=0), model_ns, model_ns)
    records = []
    for case in cases:
        value = copy.deepcopy(case["input"])
        if case.get("pairs_tuple"):
            value = [tuple(pair) for pair in value]
        if case.get("outer_tuple"):
            value = tuple(value)
        before = copy.deepcopy(value)
        answer = None
        status = "return"
        try:
            answer = model_ns["coalesce"](value)
        except ValueError:
            status = "value_error"
        except BaseException:
            status = "exception"
        # Protocol failures after the model call abort the ENTIRE assessment,
        # rather than being mistaken for the model raising ValueError.
        shape, primitive_answer = (
            normalize_interval_answer(answer)
            if status == "return" else (False, None)
        )
        records.append({
            "id": case["id"], "status": status, "shape": shape,
            "answer": primitive_answer,
            "mutated": not primitive_input_unchanged(value, before),
        })
    output = json.dumps(records, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    ) + b"\n"
    require(len(output) <= MAX_PROTOCOL_BYTES)
    sys.stdout.buffer.write(output)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        # No partial array, exception details, model repr or traceback.
        sys.stderr.write("assessor_invalid_" + stage + "_" + type(exc).__name__ + "\n")
        raise SystemExit(2)
"""


def trusted_driver_source() -> str:
    """Return source TEXT to stage in the container; does not run anything."""
    return ASSESSOR_DRIVER


# A source-based grammar lock covers every finite rule and normalization detail
# (including the trusted driver text), rather than a hand-maintained partial list.
# This reads THIS trusted file only; never an artifact or a credential source.
GRAMMAR_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
