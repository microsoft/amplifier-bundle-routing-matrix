"""Pure AST/protocol tests: NEVER compile/exec/import generated model code.

Driver source is inspected as text/AST only. Real container authenticity,
timeouts, hash mismatch execution and cleanup controls are parent-owned.
All snippets and case values below are newly authored synthetic controls.
"""

import ast
import copy
import hashlib
import sys
import textwrap
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import restricted_interval as restricted
from restricted_interval import (
    ASSESSOR_DRIVER,
    CASE_GROUPS,
    GRAMMAR_SHA256,
    GRAMMAR_VERSION,
    MAX_AST_DEPTH,
    MAX_AST_NODES,
    MAX_CASES,
    MAX_DOCSTRING_CHARS,
    MAX_FUNCTIONS,
    MAX_INPUT_DEPTH,
    MAX_INPUT_NODES,
    MAX_PROTOCOL_BYTES,
    MAX_SOURCE_BYTES,
    SAFE_BUILTIN_NAMES,
    ArtifactUngradable,
    RestrictedAdmission,
    normalize_interval_answer,
    primitive_input_unchanged,
    trusted_driver_source,
    validate_assessment_cases,
    validate_interval_module,
)


def test_large_hex_literal_hash_does_not_use_decimal_conversion():
    _, admission = validate_interval_module(
        "def coalesce(ranges):\n    large = 0x" + "f" * 4096 + "\n    return []\n"
    )
    assert len(admission.normalized_sha256) == 64


CORRECT_SOURCE = textwrap.dedent(
    '''\
    """Synthetic interval implementation."""
    def coalesce(ranges: list[list[int]]) -> list[tuple[int, int]]:
        """Validation, private sorting and merging."""
        def by_start(pair: tuple[int, int]) -> int:
            return pair[0]
        if type(ranges) is not list:
            raise ValueError("outer container")
        prepared: list[tuple[int, int]] = []
        for pair in ranges:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError("pair")
            start, stop = pair
            if type(start) is not int or type(stop) is not int or start >= stop:
                raise ValueError("endpoint")
            prepared.append((start, stop))
        prepared.sort(key=by_start, reverse=False)
        output: list[tuple[int, int]] = []
        for start, stop in prepared:
            if output and start <= output[-1][1]:
                output[-1] = (output[-1][0], max(output[-1][1], stop))
            else:
                output.append((start, stop))
        return output
    '''
)


def module_source(body: str) -> str:
    return "def coalesce(ranges):\n" + textwrap.indent(body.strip() + "\n", "    ")


def assert_refused(source: str, reason: str | None = None) -> None:
    with pytest.raises(ArtifactUngradable) as caught:
        validate_interval_module(source)
    message = str(caught.value)
    assert message.startswith("restricted_")
    assert len(message) <= 64
    assert "\n" not in message
    if reason is not None:
        assert message == reason


def test_exact_public_api_and_immutable_admission():
    tree, admission = validate_interval_module(CORRECT_SOURCE)
    assert type(tree) is ast.Module
    assert type(admission) is RestrictedAdmission
    assert issubclass(ArtifactUngradable, ValueError)
    assert tuple(field.name for field in fields(admission)) == (
        "version",
        "source_sha256",
        "normalized_sha256",
        "function_names",
    )
    assert GRAMMAR_VERSION == admission.version == "restricted-python-v1"
    assert admission.function_names == ("coalesce", "by_start")
    assert (
        admission.source_sha256
        == hashlib.sha256(CORRECT_SOURCE.encode("utf-8")).hexdigest()
    )
    from restricted_interval import normalized_digest

    assert admission.normalized_sha256 == normalized_digest(tree)
    with pytest.raises(FrozenInstanceError):
        admission.version = "other"


def test_grammar_hash_binds_trusted_source_not_artifact_or_partial_metadata():
    assert (
        GRAMMAR_SHA256
        == hashlib.sha256(Path(restricted.__file__).read_bytes()).hexdigest()
    )
    assert len(GRAMMAR_SHA256) == 64
    assert set(GRAMMAR_SHA256) <= set("0123456789abcdef")
    assert SAFE_BUILTIN_NAMES == (
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


def test_annotations_are_stripped_not_evaluated_and_hash_is_location_independent():
    annotated = textwrap.dedent(
        """\
        def coalesce(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
            def keyfn(pair: tuple[int, int]) -> int:
                return pair[0]
            output: list[tuple[int, int]] = []
            return output
        """
    )
    plain = annotated.replace(": list[tuple[int, int]]", "").replace(
        ": tuple[int, int]", ""
    )
    plain = plain.replace(" -> list[tuple[int, int]]", "").replace(" -> int", "")
    tree, admission = validate_interval_module(annotated)
    plain_tree, plain_admission = validate_interval_module(plain)
    assert ast.dump(tree) == ast.dump(plain_tree)
    assert admission.normalized_sha256 == plain_admission.normalized_sha256
    assert admission.source_sha256 != plain_admission.source_sha256
    for node in ast.walk(tree):
        assert not isinstance(node, ast.AnnAssign)
        if isinstance(node, ast.FunctionDef):
            assert node.returns is None
        if isinstance(node, ast.arg):
            assert node.annotation is None
    shifted_tree, shifted = validate_interval_module("\n# harmless comment\n" + plain)
    assert shifted.normalized_sha256 == plain_admission.normalized_sha256
    assert shifted.source_sha256 != plain_admission.source_sha256
    assert shifted_tree is not plain_tree


@pytest.mark.parametrize(
    "annotation",
    ["int", "bool", "list", "tuple", "None", "list[int]", "tuple[list[int], None]"],
)
def test_finite_annotations(annotation):
    validate_interval_module(
        f"def coalesce(ranges: {annotation}) -> {annotation}:\n    return []\n"
    )


def test_recursively_nested_annotation_tuples_are_finite():
    validate_interval_module(
        "def coalesce(ranges: list[(int, (bool, tuple[int, None]))]):\n    return []\n"
    )


@pytest.mark.parametrize(
    "annotation",
    [
        "int()",
        "ValueError('runtime call')",
        "list[abs(1)]",
        "coalesce(ranges)",
        "'list[int]'",
        "list['int']",
        "list[tuple[int, ...]]",
        "list[sys]",
        "list.__class__",
        "ranges",
        "dict",
        "int | None",
        "42",
        "True",
        "(int, bool)",
    ],
)
@pytest.mark.parametrize("site", ["parameter", "return", "assignment"])
def test_annotation_authority_is_rejected_even_if_call_is_otherwise_approved(
    annotation, site
):
    if site == "parameter":
        source = f"def coalesce(ranges: {annotation}):\n    return []\n"
    elif site == "return":
        source = f"def coalesce(ranges) -> {annotation}:\n    return []\n"
    else:
        source = module_source(f"output: {annotation} = []\nreturn output")
    assert_refused(source)


def test_value_less_annotations_rejected_and_subscript_annotations_normalized():
    assert_refused(
        module_source("output: list[int]\nreturn []"),
        "restricted_annotation_no_value",
    )
    tree, _ = validate_interval_module(
        module_source("output = []\noutput[0]: int = 3\nreturn output")
    )
    assert not any(isinstance(node, ast.AnnAssign) for node in ast.walk(tree))


@pytest.mark.parametrize(
    "body",
    [
        "return []",
        "return",
        "return coalesce(ranges)",
        "while True:\n    pass",
        "ranges.sort()\nreturn []",
        "return [(pair[0], pair[1]) for pair in ranges]",
        "return list((pair[0], pair[1]) for pair in ranges)",
        "return [(a, b) for a, b in ranges if a < b]",
        "return [(x, y) for x in range(3) for y in range(x) if y != 2]",
        "return [sum(y for y in row) for row in ranges]",
        "return [row for row in ranges for row[0] in [1]]",
        "return ranges[1:-1:2]",
        "result = ranges.copy()\nresult.extend([])\nresult.pop()\nreturn result",
        "result = []\nlist.append(result, (1, 2))\nreturn result",
        "left = right = []\n[a, (b, c)] = [1, (2, 3)]\nreturn left",
        "total = 0\nfor x in range(3):\n    total += x\nreturn []",
        "for x in ranges:\n    if x:\n        continue\n    break\nelse:\n    pass\nreturn []",
        "while ranges:\n    break\nelse:\n    pass\nreturn []",
        "return [] if not ranges else list(reversed(ranges))",
        "return [None, True, 42, -3, 1.25, 'primitive']",
        "return [(+1 + 2 - 3) * 4 // 5 % 6]",
        "return [True and False or not False]",
        "return [1 == 1 != 2 < 3 <= 4 > 0 >= -1]",
        "return [1 in ranges, 2 not in ranges, ranges is None, ranges is not None]",
        "return [len(ranges), type(ranges), isinstance(ranges, list)]",
        "return [int(True), bool(1), list(), tuple(), range(2)]",
        "return [min(1, 2), max(1, 2), sum([1, 2]), abs(-1)]",
        "return [all([True]), any([False]), enumerate(ranges, start=1)]",
        "return [zip(ranges, ranges), sorted(ranges, reverse=True)]",
        "saved = len\nreturn [saved]",
        "return ValueError('data, not an IO capability')",
        "raise ValueError()",
        "raise ValueError('literal')",
    ],
)
def test_positive_closed_syntax_including_runtime_failures_and_hang(body):
    # Admission is NOT a functional result. The hanging control is never run.
    validate_interval_module(module_source(body))


def test_positional_only_argument_and_nested_helper_recursion():
    validate_interval_module(
        "def coalesce(ranges, /):\n"
        "    def helper(item, /):\n"
        "        return helper(item) if item else []\n"
        "    return helper(ranges)\n"
    )


@pytest.mark.parametrize(
    "source",
    [
        "",
        "{}",
        "[]",
        "42",
        "pass",
        "import os\n" + module_source("return []"),
        "value = []\n" + module_source("return []"),
        module_source("return []") + "coalesce([])\n",
        module_source("return []") + "def extra(x):\n    return x\n",
        "def other(ranges):\n    return []\n",
        "async def coalesce(ranges):\n    return []\n",
        "@list\n" + module_source("return []"),
        "def coalesce():\n    return []\n",
        "def coalesce(items):\n    return []\n",
        "def coalesce(ranges, other):\n    return []\n",
        "def coalesce(ranges=[]):\n    return []\n",
        "def coalesce(*ranges):\n    return []\n",
        "def coalesce(ranges, **kw):\n    return []\n",
        "def coalesce(*, ranges):\n    return []\n",
        module_source("def helper(x=1):\n    return x\nreturn []"),
        module_source("def helper(*items):\n    return items\nreturn []"),
        module_source("def helper(**items):\n    return items\nreturn []"),
        module_source("def helper(*, item):\n    return item\nreturn []"),
        module_source("@list\ndef helper(item):\n    return item\nreturn []"),
        module_source("def helper(x, x):\n    return x\nreturn []"),
        module_source("def len(item):\n    return item\nreturn []"),
        module_source("def helper(x):\n    return x\ndef helper(y):\n    return y"),
        module_source(
            "def helper(x):\n    def helper(y):\n        return y\nreturn []"
        ),
        module_source("def coalesce(item):\n    return item\nreturn []"),
        module_source("return []  # type: ignore"),
        module_source("output = []  # type: list[int]\nreturn output"),
    ],
)
def test_module_and_function_refusals(source):
    assert_refused(source)


@pytest.mark.parametrize(
    "body",
    [
        # Retained original escape, not a weaker grep-only substitute.
        "g = coalesce.__globals__\nreturn []",
        "return __builtins__",
        "return globals()",
        "return locals()",
        "return vars(coalesce)",
        "return dir(ranges)",
        "return getattr(coalesce, '__globals__')",
        "setattr(coalesce, '__globals__', ranges)\nreturn []",
        "delattr(coalesce, '__name__')\nreturn []",
        "return eval('1')",
        "return exec('pass')",
        "return compile('pass', 'x', 'exec')",
        "return open('file')",
        "print('forged protocol')\nreturn []",
        "return input()",
        "return __import__('sys')",
        "return object()",
        "return help()",
        "return breakpoint()",
        "return sys.stdout",
        "return '{0.__globals__}'.format(coalesce)",
        "return 'x'.format_map(ranges)",
        "return list.mro()",
        "return type(ranges).__bases__",
        "return coalesce.__code__",
        "return ranges.__class__",
        "return (1).__class__",
        "return ranges.append",
        "ranges.append",
        "saved = ranges.append\nreturn []",
        "saved = len\nreturn saved(ranges)",
        "def helper(item):\n    return item\nsaved = helper\nreturn saved(ranges)",
        "return [len][0](ranges)",
        "return type(ranges)(ranges)",
        "return (len if ranges else tuple)(ranges)",
        "return (lambda item: item)(ranges)",
        "return type()",
        "return type('X', (), [])",
        "return type(ranges, ranges)",
        "return type(object=ranges)",
        "return type(*ranges)",
        "return type(**ranges)",
        "return sorted(*ranges)",
        "return sorted(ranges, **ranges)",
        "return ValueError(1)",
        "return ValueError(ranges)",
        "return ValueError('a' + 'b')",
        "return ValueError('a', 'b')",
        "return ValueError(message='a')",
        "raise",
        "raise ranges",
        "raise ValueError('x') from None",
        "raise ValueError('x') from ValueError()",
    ],
)
def test_reflection_io_indirect_calls_and_raise_refusals(body):
    assert_refused(module_source(body))


@pytest.mark.parametrize(
    "body",
    [
        "import os\nreturn []",
        "from os import path\nreturn []",
        "global ranges\nreturn []",
        "nonlocal ranges\nreturn []",
        "class Thing:\n    pass\nreturn []",
        "async def helper(item):\n    return item\nreturn []",
        "try:\n    return []\nexcept ValueError:\n    return []",
        "with ranges:\n    pass\nreturn []",
        "yield []",
        "yield from ranges",
        "return await ranges",
        "del ranges[0]\nreturn []",
        "return (x := ranges)",
        "return [x async for x in ranges]",
        "return {'answer': []}",
        "return {1, 2}",
        "return {x for x in ranges}",
        "return {x: x for x in ranges}",
        "return [*ranges]",
        "first, *rest = ranges\nreturn []",
        "return f'{ranges}'",
        "return b'bytes'",
        "return ...",
        "return 2j",
        "return 1e10000",
        "return 2 ** 10",
        "return 4 / 2",
        "return 1 << 2",
        "return 1 & 2",
        "return 1 @ 2",
        "return ~1",
        "ranges.attr = []\nreturn []",
        "ranges.append = []\nreturn []",
        "ranges.append += []\nreturn []",
        "42\nreturn []",
        "ranges[0]\nreturn []",
        "return []\n'later docstring'",
        "if ranges:\n    'not a docstring'\nreturn []",
        "break\nreturn []",
        "continue\nreturn []",
        "while ranges:\n    def helper(item):\n        break\nreturn []",
        "while ranges:\n    pass\nelse:\n    break\nreturn []",
        "match ranges:\n    case []:\n        pass\nreturn []",
    ],
)
def test_unknown_or_excluded_ast_features_fail_closed(body):
    assert_refused(module_source(body))


@pytest.mark.parametrize("name", [*SAFE_BUILTIN_NAMES, "coalesce", "helper"])
@pytest.mark.parametrize(
    "binding",
    [
        "{name} = ranges",
        "{name}: list = ranges",
        "{name} += ranges",
        "[item, ({name}, other)] = ranges",
        "for {name} in ranges:\n    pass",
        "for item, {name} in ranges:\n    pass",
        "result = [item for {name} in ranges for item in ranges]",
        "result = list(item for {name} in ranges for item in ranges)",
        "def consumer({name}):\n    return []",
    ],
)
def test_every_builtin_or_function_binding_site_is_protected(name, binding):
    body = (
        "def helper(item):\n    return item\n"
        + binding.format(name=name)
        + "\nreturn []"
    )
    assert_refused(module_source(body))


@pytest.mark.parametrize("name", ["_private", "has__dunder", "__builtins__"])
@pytest.mark.parametrize(
    "body",
    [
        "{name} = []\nreturn []",
        "return {name}",
        "for {name} in ranges:\n    pass\nreturn []",
        "return [item for {name} in ranges for item in ranges]",
        "def helper({name}):\n    return []\nreturn []",
        "def {name}(item):\n    return []\nreturn []",
    ],
)
def test_private_names_denied_at_load_and_all_bindings(name, body):
    assert_refused(module_source(body.format(name=name)))


@pytest.mark.parametrize(
    "name",
    ["records", "cases", "sys", "json", "copy", "ast", "model_ns", "admission"],
)
def test_unbound_driver_names_refused_but_model_local_names_allowed(name):
    assert_refused(module_source(f"return {name}"), "restricted_unbound_name")
    validate_interval_module(module_source(f"{name} = []\nreturn {name}"))
    validate_interval_module(
        module_source(f"def helper({name}):\n    return {name}\nreturn helper(ranges)")
    )


def test_conditional_locals_enclosing_scopes_and_helper_visibility():
    validate_interval_module(
        module_source(
            "if ranges:\n    records = []\n"
            "def outer(item):\n"
            "    def inner(pair):\n"
            "        return records if pair else item\n"
            "    return inner(item)\n"
            "return outer(ranges)"
        )
    )
    assert_refused(
        module_source(
            "def outer(item):\n"
            "    def inner(pair):\n"
            "        return pair\n"
            "    return inner(item)\n"
            "return inner(ranges)"
        ),
        "restricted_unbound_name",
    )
    assert_refused(
        module_source(
            "def outer(item):\n    secret = []\n    return secret\nreturn secret"
        ),
        "restricted_unbound_name",
    )


def test_comprehensions_are_separate_lexical_scopes_not_global_name_loopholes():
    assert_refused(
        module_source("result = [x for x in ranges]\nreturn x"),
        "restricted_unbound_name",
    )
    assert_refused(
        module_source("return [cases for cases in cases]"),
        "restricted_unbound_name",
    )
    assert_refused(
        module_source("return [x for x in ranges if records]"),
        "restricted_unbound_name",
    )
    assert_refused(
        module_source("return [x for x in ranges for y in cases]"),
        "restricted_unbound_name",
    )
    validate_interval_module(
        module_source(
            "cases = ranges\nrecords = []\n"
            "return [cases for cases in cases if not records]"
        )
    )
    # A later target is lexically local even if read before its first binding;
    # any resulting unbound-local exception is a runtime functional outcome.
    validate_interval_module(module_source("return [x for x in ranges for y in y]"))


def test_helper_key_sorting_and_literal_boolean_reverse():
    body = (
        "def keyfn(pair):\n    return pair[0]\n"
        "result = sorted(ranges, key=keyfn, reverse=True)\n"
        "result.sort(key=keyfn, reverse=False)\n"
        "return result"
    )
    validate_interval_module(module_source(body))
    validate_interval_module(module_source("return list(enumerate(ranges, start=1))"))


@pytest.mark.parametrize(
    "call",
    [
        "sorted(ranges, key=len)",
        "sorted(ranges, key=coalesce)",
        "sorted(ranges, key=None)",
        "sorted(ranges, key=saved)",
        "sorted(ranges, key=[keyfn][0])",
        "sorted(ranges, key=keyfn(ranges))",
        "sorted(ranges, reverse=1)",
        "sorted(ranges, reverse=None)",
        "sorted(ranges, reverse=bool(1))",
        "sorted(ranges, reverse=flag)",
        "sorted(ranges, reverse=True, reverse=False)",
        "sorted(ranges, start=1)",
        "ranges.sort(key=saved)",
        "ranges.sort(reverse=0)",
        "ranges.sort(start=1)",
        "ranges.append(value=1)",
        "ranges.extend(iterable=[])",
        "ranges.copy(reverse=True)",
        "ranges.pop(index=0)",
        "enumerate(ranges, key=keyfn)",
        "enumerate(ranges, reverse=True)",
        "len(ranges, start=1)",
        "keyfn(pair=ranges)",
        "coalesce(ranges=ranges)",
        "sum(ranges, start=1)",
        "min(ranges, key=keyfn)",
    ],
)
def test_keywords_and_sort_callbacks_are_strict(call):
    body = (
        "def keyfn(pair):\n    return pair[0]\n"
        "saved = keyfn\nflag = True\n"
        f"return {call}"
    )
    assert_refused(module_source(body))


def test_out_of_scope_sort_helper_is_not_an_approved_global():
    assert_refused(
        module_source(
            "def outer(item):\n"
            "    def keyfn(pair):\n"
            "        return pair[0]\n"
            "    return item\n"
            "return sorted(ranges, key=keyfn)"
        ),
        "restricted_unbound_name",
    )


def test_exact_source_byte_limit_including_multibyte_utf8():
    base = module_source("return []")
    exact = base + "#" + "x" * (MAX_SOURCE_BYTES - len(base.encode()) - 1)
    assert len(exact.encode("utf-8")) == MAX_SOURCE_BYTES
    validate_interval_module(exact)
    assert_refused(exact + "x", "restricted_source_bytes")
    multibyte = base + "#" + "é" * (MAX_SOURCE_BYTES // 2)
    assert len(multibyte) < MAX_SOURCE_BYTES
    assert_refused(multibyte, "restricted_source_bytes")


def test_ast_node_limit_counts_contexts_and_all_nodes_before_normalization():
    base = module_source("return []")
    baseline_count = sum(1 for _ in ast.walk(ast.parse(base)))
    padding = MAX_AST_NODES - baseline_count
    exact = "def coalesce(ranges):\n    " + "pass;" * padding + "\n    return []\n"
    assert len(exact.encode()) < MAX_SOURCE_BYTES
    assert sum(1 for _ in ast.walk(ast.parse(exact))) == MAX_AST_NODES
    validate_interval_module(exact)
    assert_refused(exact + "    pass\n", "restricted_ast_nodes")


def tree_depth(tree):
    stack = [(tree, 1)]
    maximum = 0
    while stack:
        node, depth = stack.pop()
        maximum = max(maximum, depth)
        stack.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    return maximum


def test_ast_depth_exact_bound():
    # Module/FunctionDef/Return/Constant have depths 1/2/3/4 respectively.
    exact = module_source("return " + "-" * (MAX_AST_DEPTH - 4) + "1")
    assert tree_depth(ast.parse(exact)) == MAX_AST_DEPTH
    validate_interval_module(exact)
    assert_refused(
        module_source("return " + "-" * (MAX_AST_DEPTH - 3) + "1"),
        "restricted_ast_depth",
    )


def test_function_count_limit_is_total_not_per_scope():
    helpers = "".join(
        f"def helper{index}(item):\n    return item\n"
        for index in range(MAX_FUNCTIONS - 1)
    )
    _, admission = validate_interval_module(module_source(helpers + "return []"))
    assert len(admission.function_names) == MAX_FUNCTIONS
    assert_refused(
        module_source(helpers + "def another(item):\n    return item\nreturn []"),
        "restricted_functions",
    )


@pytest.mark.parametrize("site", ["module", "function", "helper"])
def test_docstring_character_bound_and_location(site):
    def source_for(length):
        literal = repr("d" * length)
        if site == "module":
            return literal + "\n" + module_source("return []")
        if site == "function":
            return module_source(literal + "\nreturn []")
        return module_source(
            "def helper(item):\n    " + literal + "\n    return item\nreturn []"
        )

    validate_interval_module(source_for(MAX_DOCSTRING_CHARS))
    assert_refused(source_for(MAX_DOCSTRING_CHARS + 1), "restricted_docstring")


@pytest.mark.parametrize(
    "source",
    [
        None,
        b"def coalesce(ranges): return []",
        3,
        "\ud800",
        "def coalesce(ranges):\n    return [\n",
        "def coalesce(ranges):\n\t pass\n    return []\n",
        "def coalesce(ranges):\n    return \x00\n",
        '{"malformed": ',
        "def coalesce(ranges):\n    return " + "(" * 300 + "1" + ")" * 300,
    ],
)
def test_malformed_or_unbounded_parser_inputs_have_sanitized_errors(source):
    assert_refused(source)


def test_parser_errors_do_not_echo_artifact_content():
    marker = "SYNTHETIC_DO_NOT_ECHO"
    with pytest.raises(ArtifactUngradable) as caught:
        validate_interval_module(module_source(f"return ({marker}"))
    assert marker not in str(caught.value)
    assert str(caught.value) == "restricted_source_parse"


def protocol_cases():
    return [
        {
            "id": "0",
            "group": "union",
            "input": [[-3, 2], [2, 4]],
            "invalid": False,
            "pairs_tuple": True,
        },
        {"id": "1", "group": "touching_empty", "input": [], "invalid": False},
        {"id": "2", "group": "invalid", "input": None, "invalid": True},
        {
            "id": "3",
            "group": "immutability",
            "input": [[7, 9], [1, 3]],
            "invalid": False,
        },
    ]


def test_case_protocol_is_independent_fresh_primitives_without_expected_keys():
    cases = protocol_cases()
    result = validate_assessment_cases(cases)
    assert result == cases
    assert result is not cases
    assert result[0] is not cases[0]
    assert result[0]["input"] is not cases[0]["input"]
    assert result[0]["input"][0] is not cases[0]["input"][0]
    result[0]["input"][0][0] = -99
    assert cases[0]["input"][0][0] == -3
    assert {case["group"] for case in cases} == CASE_GROUPS


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        3,
        "ranges",
        [1],
        [[1]],
        [[1, 2, 3]],
        [[True, 2]],
        [[0, False]],
        [[1.0, 2]],
        [["1", 2]],
        [[2, 2]],
        [[4, -2]],
    ],
)
def test_intentionally_invalid_interval_values_are_valid_primitive_case_inputs(value):
    cases = protocol_cases()
    cases[2]["input"] = value
    assert validate_assessment_cases(cases)[2]["input"] == value


@pytest.mark.parametrize(
    "changes",
    [
        {"expected": [[-3, 4]]},
        {"answer": []},
        {"awards": {"union": 1}},
        {"unknown": True},
        {"id": None},
        {"id": 1},
        {"id": ""},
        {"id": "x" * 65},
        {"group": "missing"},
        {"group": []},
        {"invalid": 1},
        {"pairs_tuple": 1},
        {"outer_tuple": "true"},
        {"pairs_tuple": True, "input": None},
        {"pairs_tuple": True, "input": [1]},
        {"outer_tuple": True, "input": 1},
    ],
)
def test_malformed_case_fields_flags_and_expected_keys_refused(changes):
    cases = protocol_cases()
    cases[0].update(changes)
    with pytest.raises(ArtifactUngradable, match="^assessor_"):
        validate_assessment_cases(cases)


@pytest.mark.parametrize("field", ["id", "group", "input", "invalid"])
def test_required_case_fields_cannot_be_omitted(field):
    cases = protocol_cases()
    del cases[0][field]
    with pytest.raises(ArtifactUngradable, match="assessor_case_fields"):
        validate_assessment_cases(cases)


def test_empty_partial_duplicate_nonarray_and_case_count_bounds():
    for bad in (None, {}, [], protocol_cases()[:-1], [None]):
        with pytest.raises(ArtifactUngradable, match="^assessor_"):
            validate_assessment_cases(bad)
    cases = protocol_cases()
    cases[1]["id"] = cases[0]["id"]
    with pytest.raises(ArtifactUngradable, match="assessor_case_id"):
        validate_assessment_cases(cases)
    groups = sorted(CASE_GROUPS)
    maximum = [
        {
            "id": str(index),
            "group": groups[index % len(groups)],
            "input": [],
            "invalid": False,
        }
        for index in range(MAX_CASES)
    ]
    validate_assessment_cases(maximum)
    with pytest.raises(ArtifactUngradable, match="assessor_cases"):
        validate_assessment_cases(maximum + [maximum[0]])


@pytest.mark.parametrize(
    "value",
    [
        (1, 2),
        b"bytes",
        float("nan"),
        float("inf"),
        {1: []},
        {"nested": float("-inf")},
        [None] * MAX_INPUT_NODES,
    ],
)
def test_nonprimitive_and_oversize_case_values_refused(value):
    cases = protocol_cases()
    cases[2]["input"] = value
    with pytest.raises(ArtifactUngradable, match="^assessor_input_"):
        validate_assessment_cases(cases)


def test_case_depth_and_cycles_are_bounded_without_execution():
    cases = protocol_cases()
    value = 0
    for _ in range(MAX_INPUT_DEPTH - 1):
        value = [value]
    cases[2]["input"] = value
    validate_assessment_cases(cases)
    cases[2]["input"] = [value]
    with pytest.raises(ArtifactUngradable, match="assessor_input_bound"):
        validate_assessment_cases(cases)
    cycle = []
    cycle.append(cycle)
    cases[2]["input"] = cycle
    with pytest.raises(ArtifactUngradable, match="assessor_input_bound"):
        validate_assessment_cases(cases)


def test_exact_primitive_mutation_observation_including_cycles_and_bool_aliasing():
    values = [None, {}, 3, "ranges", [[1, 2]], [(1, 2)], ((1, 2),)]
    for value in values:
        assert primitive_input_unchanged(value, copy.deepcopy(value))
    assert not primitive_input_unchanged([[True, 2]], [[1, 2]])
    assert not primitive_input_unchanged([(1, 2)], [[1, 2]])
    assert not primitive_input_unchanged([[1, 4]], [[1, 2]])
    assert not primitive_input_unchanged([[1, 2], [3, 4]], [[3, 4], [1, 2]])
    assert not primitive_input_unchanged([[len, 2]], [[1, 2]])
    cycle = []
    cycle.append(cycle)
    assert not primitive_input_unchanged(cycle, [[1, 2]])
    assert not primitive_input_unchanged(cycle, cycle)


@pytest.mark.parametrize(
    "answer",
    [
        None,
        (),
        ((1, 2),),
        [[1, 2]],
        [(1,)],
        [(1, 2, 3)],
        [(True, 2)],
        [(1, False)],
        [(1.0, 2)],
        [(len, 2)],
        [{"a": 1}],
    ],
)
def test_shape_observation_requires_exact_list_tuple_pair_and_nonbool_int(answer):
    assert normalize_interval_answer(answer) == (False, None)


def test_answer_conversion_is_a_fresh_driver_owned_copy_and_is_bounded():
    answer = [(-2, 4), (7, 9)]
    shape, primitive = normalize_interval_answer(answer)
    assert shape is True
    assert primitive == [[-2, 4], [7, 9]]
    primitive[0][0] = -99
    assert answer == [(-2, 4), (7, 9)]
    assert normalize_interval_answer([]) == (True, [])
    with pytest.raises(ArtifactUngradable, match="assessor_output_bound"):
        normalize_interval_answer([(1, 2)] * (MAX_PROTOCOL_BYTES + 1))


def test_host_module_has_no_artifact_execution_or_live_smoke_dependency():
    # This parses trusted source; the driver Constant is not traversed as code.
    trusted_tree = ast.parse(Path(restricted.__file__).read_text(encoding="utf-8"))
    forbidden = {"exec", "compile", "eval", "__import__"}
    for node in ast.walk(trusted_tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden
        if isinstance(node, ast.ImportFrom):
            assert node.module != "live_smoke"
        if isinstance(node, ast.Import):
            assert all(alias.name != "live_smoke" for alias in node.names)


def test_driver_text_revalidates_locks_before_its_only_model_exec_site():
    # Static wiring regression only, NOT proof of container execution.
    assert trusted_driver_source() == ASSESSOR_DRIVER
    driver_tree = ast.parse(ASSESSOR_DRIVER)
    calls = [
        node
        for node in ast.walk(driver_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    exec_calls = [node for node in calls if node.func.id == "exec"]
    compile_calls = [node for node in calls if node.func.id == "compile"]
    assert len(exec_calls) == len(compile_calls) == 1
    assert exec_calls[0].args[0] is compile_calls[0]
    assert [arg.id for arg in exec_calls[0].args[1:]] == ["model_ns", "model_ns"]
    assert compile_calls[0].args[0].id == "normalized"
    assert not any(node.func.id in {"globals", "locals"} for node in calls)
    exec_position = ASSESSOR_DRIVER.index("exec(compile(normalized")
    for check in (
        "require(locks[2] == GRAMMAR_SHA256)",
        "normalized, admission = validate_interval_module(",
        "require(admission.version == GRAMMAR_VERSION)",
        "require(admission.source_sha256 == locks[0])",
        "require(admission.normalized_sha256 == locks[1])",
        "cases = validate_assessment_cases(",
    ):
        assert ASSESSOR_DRIVER.index(check) < exec_position
    assert (
        "name: getattr(builtins, name) for name in SAFE_BUILTIN_NAMES"
        in ASSESSOR_DRIVER
    )
    assert 'model_ns = {"__builtins__": {' in ASSESSOR_DRIVER
    assert 'model_ns["coalesce"](value)' in ASSESSOR_DRIVER
    assert "importlib" not in ASSESSOR_DRIVER


def test_driver_protocol_uses_trusted_shape_and_mutation_then_one_bounded_array():
    assert "read(MAX_SOURCE_BYTES + 1)" in ASSESSOR_DRIVER
    assert "read(MAX_PROTOCOL_BYTES + 1)" in ASSESSOR_DRIVER
    assert "object_pairs_hook=unique_object" in ASSESSOR_DRIVER
    assert "parse_constant=reject_constant" in ASSESSOR_DRIVER
    assert "normalize_interval_answer(answer)" in ASSESSOR_DRIVER
    assert "not primitive_input_unchanged(value, before)" in ASSESSOR_DRIVER
    assert "except ValueError:" in ASSESSOR_DRIVER
    assert "except BaseException:" in ASSESSOR_DRIVER
    assert 'status = "value_error"' in ASSESSOR_DRIVER
    assert 'status = "exception"' in ASSESSOR_DRIVER
    assert ASSESSOR_DRIVER.count("sys.stdout.buffer.write(output)") == 1
    assert "require(len(output) <= MAX_PROTOCOL_BYTES)" in ASSESSOR_DRIVER
    assert "allow_nan=False" in ASSESSOR_DRIVER
    assert (
        'sys.stderr.write("assessor_invalid_" + stage + "_" + type(exc).__name__ + "\\n")'
        in ASSESSOR_DRIVER
    )
    assert "raise SystemExit(2)" in ASSESSOR_DRIVER
    # No expected answer generator/keys are embedded or accepted by this driver.
    assert "grid_union" not in ASSESSOR_DRIVER
    assert 'case["expected"]' not in ASSESSOR_DRIVER
    assert 'case["answer"]' not in ASSESSOR_DRIVER
