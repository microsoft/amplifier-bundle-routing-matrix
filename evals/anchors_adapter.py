"""Foundation-hosted real Anchors repair, not app-cli qualification.

Loads the complete stock Anchors bundle closure from explicit immutable local
sources, then applies a declared evaluation profile: only builder and standard
development tools; no logging/CI/UI hooks or unrelated tool egress. Parent must
run the solver in a credential-free network namespace with a qualified external
controller receiver. This library never provisions isolation or reads credentials.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from anchors_transport import Policy, Transport, VERSION
from interval_repair import stage_task, snapshot_artifact
from source_locks import SourceLock
from live_transport import canonical, fingerprint, httpx, require

TOOLS = ("tool-filesystem", "tool-search", "tool-bash")
ROOT_TOOLS = ("tool-delegate",)
WORKER_EXPORTS = {"read_file", "write_file", "edit_file", "grep", "glob", "bash"}
TASK_INSTRUCTION = (
    "Read instructions.txt. Repair intervals.py and retain test_regression.py. "
    "Use python -B -m unittest for local verification. Do not modify public tests."
)
DELEGATE_ARGUMENTS = {
    "agent": "anchors:builder",
    "instruction": TASK_INSTRUCTION,
    "context_depth": "none",
}


def require_distinct_arms(first_resolution, second_resolution):
    """Compare post-resolver assigned settings, never scores or observed tool trees."""
    require(
        fingerprint(first_resolution) != fingerprint(second_resolution),
        "inheritance_erased_arms",
    )


def repository_digest(path):
    ignored = {
        ".git",
        ".anchors-venv",
        ".anchors-offline-venv",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".eval-deps",
        "target",
        "build",
        "dist",
    }
    files = []
    for file in sorted(Path(path).rglob("*")):
        relative = file.relative_to(path)
        if any(p in ignored or p.endswith(".egg-info") for p in relative.parts):
            continue
        require(not file.is_symlink(), "source_symlink")
        if file.is_file() and file.suffix not in {".pyc", ".pyo"}:
            require(
                file.stat().st_size < 64 * 1024 * 1024 and len(files) < 8192,
                "source_inventory_bound",
            )
            files.append(
                (relative.as_posix(), hashlib.sha256(file.read_bytes()).hexdigest())
            )
    require(bool(files), "source_inventory_empty")
    return fingerprint(files)


@dataclass(frozen=True)
class RepositoryLock(SourceLock):
    def validate(self):
        require(self.path.is_dir() and self.path.resolve() == self.path, "source_root")
        require(repository_digest(self.path) == self.sha256, "source_changed")


@dataclass(frozen=True)
class Sources:
    """Parent's private local source map; hashes are never public exports."""

    repositories: tuple[tuple[str, SourceLock], ...]
    runtime: tuple[tuple[str, SourceLock], ...] = ()

    def validate_runtime(self):
        modules = {
            "core": "amplifier_core",
            "foundation": "amplifier_foundation",
            "provider": "amplifier_module_provider_openai",
            "sdk": "openai",
            "httpx": "httpx2",
            "loop": "amplifier_module_loop_streaming",
            "context": "amplifier_module_context_simple",
            "delegate": "amplifier_module_tool_delegate",
            "filesystem": "amplifier_module_tool_filesystem",
            "search": "amplifier_module_tool_search",
            "bash": "amplifier_module_tool_bash",
            "routing": "amplifier_module_hooks_routing",
            "shim": "amplifier_module_eval_openai",
            "core_native": "amplifier_core._engine",
        }
        require(
            len(self.runtime) == len(modules)
            and set(dict(self.runtime)) == set(modules),
            "runtime_inventory",
        )
        for name, lock in self.runtime:
            lock.validate()
            loaded = Path(importlib.import_module(modules[name]).__file__).resolve()
            require(
                loaded == lock.path
                if lock.path.is_file()
                else loaded.is_relative_to(lock.path),
                "runtime_source",
            )

    def validate(self):
        names = [n for n, _ in self.repositories]
        require(len(names) == len(set(names)) and len(names) <= 32, "source_map")
        for _, lock in self.repositories:
            lock.validate()

    def root(self, name):
        matches = [s.path for n, s in self.repositories if n == name]
        require(len(matches) == 1, "source_missing")
        return matches[0]

    def resolve(self, uri):
        if not uri.startswith("git+https://github.com/microsoft/"):
            require(
                not uri.startswith(("http:", "https:", "git+")), "source_unsupported"
            )
            return None
        parsed = urlsplit(uri[4:])
        name = parsed.path.rsplit("/", 1)[-1].split("@", 1)[0].removesuffix(".git")
        root = self.root(name)
        fragment = parse_qs(parsed.fragment)
        require(set(fragment) <= {"subdirectory"}, "source_fragment")
        relative = fragment.get("subdirectory", [""])[0]
        selected = (root / relative).resolve()
        require(
            selected.is_relative_to(root.resolve()) and selected.exists(), "source_path"
        )
        return str(selected)

    def pin(self, value):
        if isinstance(value, dict):
            return {k: self.pin(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.pin(v) for v in value]
        if isinstance(value, str) and value.startswith("git+"):
            return self.resolve(value)
        return value


async def load_anchors(sources, cache):
    from amplifier_foundation import load_bundle
    from amplifier_foundation.registry import BundleRegistry

    sources.validate()
    registry = BundleRegistry(
        home=cache,
        strict=True,
        persist=False,
        read_persisted=False,
        include_source_resolver=sources.resolve,
    )
    registry.register(
        {
            "foundation": str(sources.root("amplifier-foundation")),
            "routing-matrix": str(sources.root("amplifier-bundle-routing-matrix")),
        }
    )
    bundle = await load_bundle(
        str(sources.root("amplifier-foundation") / "bundles/anchors.md"),
        registry=registry,
    )
    bundle.load_agent_metadata()
    require(
        bundle.name == "anchors" and "anchors:builder" in bundle.agents,
        "real_anchors_missing",
    )
    builder = bundle.agents["anchors:builder"]
    require(
        builder.get("model_role", builder.get("meta", {}).get("model_role"))
        == ["coding", "general"],
        "builder_role",
    )
    # Pin full declared module/tool/config closure BEFORE removing side channels.
    bundle = replace(
        bundle,
        session=sources.pin(bundle.session),
        tools=sources.pin(bundle.tools),
        hooks=sources.pin(bundle.hooks),
        agents=sources.pin(bundle.agents),
        providers=[],
    )
    return bundle


def model_config(model, effort, output=4096, timeout=60):
    require(effort in {"low", "medium", "high", "xhigh"}, "native_effort")
    return {
        "eval_profile": VERSION,
        "default_model": model,
        "reasoning_effort": effort,
        "priority": 0,
        "max_output_tokens": output,
        "max_retries": 0,
        "auto_continue": False,
        "use_streaming": False,
        "timeout": timeout,
        "close_timeout": 10,
        "reasoning_replay_scope": "none",
        "extra_request_params": {"service_tier": "default", "include": []},
    }


def profile(stock, sources, workspace, matrix_dir, config, worker=False):
    """Explicit ablation of non-task surfaces, preserving actual Anchors content."""
    tools = []
    for item in stock.tools:
        if item["module"] not in (TOOLS if worker else ROOT_TOOLS):
            continue
        item = copy.deepcopy(item)
        if item["module"] == "tool-delegate":
            item["config"] = {
                "features": {
                    "self_delegation": {"enabled": False},
                    "session_resume": {"enabled": False},
                    "provider_selection": {"enabled": False},
                },
                "settings": {
                    "timeout": 1100,
                    "max_llm_calls": 22,
                    "exclude_tools": ["tool-delegate"],
                },
            }
        else:
            item["config"] = {"working_dir": str(workspace)}
        tools.append(item)
    require(
        {t["module"] for t in tools} == set(TOOLS if worker else ROOT_TOOLS),
        "stock_tools_missing",
    )
    builder = stock.agents["anchors:builder"]
    instruction = builder.get(
        "instruction", builder.get("context", {}).get("instruction", "")
    )
    require(isinstance(instruction, str) and bool(instruction), "builder_instruction")
    return replace(
        stock,
        session={
            **stock.session,
            "orchestrator": {
                **stock.session["orchestrator"],
                "config": {"max_iterations": 24},
            },
            "context": {**stock.session["context"], "config": {"auto_compact": False}},
        },
        tools=tools,
        hooks=[
            {
                "module": "hooks-routing",
                "source": str(
                    sources.root("amplifier-bundle-routing-matrix")
                    / "modules/hooks-routing"
                ),
                "config": {
                    "default_matrix": "anchors-eval",
                    "custom_routing_dirs": [str(matrix_dir)],
                },
            }
        ],
        providers=[
            {
                "module": "provider-openai",
                "source": str(
                    sources.root("amplifier-bundle-routing-matrix")
                    / "evals/live_provider"
                ),
                "config": config,
            }
        ],
        agents={} if worker else {"anchors:builder": copy.deepcopy(builder)},
        instruction=instruction if worker else stock.instruction,
        spawn={},
    )


class AnchorsRun:
    """Injected receiver owns upstream credentials; solver gets only inert SDK auth."""

    def __init__(
        self,
        sources,
        authority,
        workspace,
        matrix_dir,
        cell_id,
        root_model,
        worker_model,
        root_effort,
        worker_effort,
        receiver_factory,
    ):
        require(callable(receiver_factory), "external_controller_receiver_required")
        require((root_model, root_effort) and worker_model, "models_required")
        self.sources, self.authority = sources, authority
        self.workspace, self.matrix_dir = Path(workspace), Path(matrix_dir)
        self.cell_id = cell_id
        self.root_model, self.worker_model = root_model, worker_model
        self.root_effort, self.worker_effort = root_effort, worker_effort
        self.receiver_factory = receiver_factory
        self.sessions, self.clients, self.factories, self.providers = [], [], {}, {}
        self.logical, self.policies = {}, {}
        self.called = self.completed = False
        self.protocol_error = False
        self.delegate_attempts = 0
        self.resolution = None
        self.wire = {}

    def verify(self, session):
        self.sources.validate()
        self.sources.validate_runtime()
        c = session.coordinator
        require(
            c.get_capability("anchors.provider_factory")
            is self.factories[session.session_id],
            "factory_authority_changed",
        )
        require(
            c.get("providers") == {"openai": self.providers[session.session_id]},
            "provider_registry",
        )
        require(
            c.get_capability("model_role_resolver").matrix_path
            == str(self.matrix_dir / "anchors-eval.yaml"),
            "routing_provenance",
        )
        require(
            fingerprint(self.matrix)
            == fingerprint(
                __import__("yaml").safe_load(
                    (self.matrix_dir / "anchors-eval.yaml").read_text()
                )
            ),
            "matrix_changed",
        )
        require(
            set(c.get("tools")) == set(self.wire[bool(session.parent_id)]),
            "tools_changed",
        )
        if session.parent_id:
            require(
                c.get_capability("session.spawn") is None
                and session.parent_id == self.sessions[0].session_id,
                "child_nonrecursive",
            )

    async def before_initialize(self, session):
        from amplifier_core.models import HookResult
        from amplifier_module_provider_openai import OpenAIProvider
        from openai import AsyncOpenAI

        self.sessions.append(session)
        child = bool(session.parent_id)
        config = model_config(
            self.worker_model if child else self.root_model,
            self.worker_effort if child else self.root_effort,
            self.authority.ledger.limits.output_max,
            self.authority.timeout_s,
        )

        async def fatal(coordinator, mounted_config, error):
            require(False, "provider_mount_failed")

        async def before_load(coordinator, mounted_config):
            require(
                coordinator is session.coordinator
                and coordinator.get_capability("anchors.provider_factory")
                is self.factories[session.session_id],
                "factory_authority_missing",
            )

        async def request_id(event, data):
            require(isinstance(data.get("request_id"), str), "logical_id_missing")
            self.logical[session.session_id] = data["request_id"]
            return HookResult()

        async def guard_delegate(event, data):
            if not child:
                self.delegate_attempts += 1
                if (
                    self.delegate_attempts != 1
                    or data.get("tool_name") != "delegate"
                    or data.get("tool_input") != DELEGATE_ARGUMENTS
                ):
                    self.protocol_error = True
                    return HookResult(action="deny", reason="fixed_root_protocol")
            return HookResult()

        def factory(coordinator, mounted_config):
            require(
                coordinator is session.coordinator and mounted_config == config,
                "factory_config",
            )
            # Exact stock tool schemas are attached after actual mounts, before send.
            policy = Policy(
                self.cell_id,
                session.session_id,
                session.parent_id,
                "coding" if child else "controller",
                "worker" if child else "root",
                config["default_model"],
                config["reasoning_effort"],
            )
            transport = Transport(
                self.authority,
                policy,
                lambda: self.prepare_wire(session),
                lambda: self.logical.get(session.session_id),
                self.receiver_factory(policy),
            )
            http = httpx.AsyncClient(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
                timeout=self.authority.timeout_s,
            )
            sdk = AsyncOpenAI(
                api_key="inert-evaluation-auth",
                base_url=self.authority.endpoint,
                max_retries=0,
                http_client=http,
                timeout=self.authority.timeout_s,
            )
            self.clients.append((sdk, http, transport))
            provider_config = {k: v for k, v in config.items() if k != "eval_profile"}
            provider = OpenAIProvider(
                "inert-evaluation-auth",
                config=provider_config,
                coordinator=coordinator,
                client=sdk,
            )
            self.providers[session.session_id] = provider
            self.policies[session.session_id] = transport
            return provider

        self.factories[session.session_id] = factory
        session.coordinator.register_capability("anchors.provider_factory", factory)
        session.coordinator.register_capability("provider.before_load", before_load)
        session.coordinator.register_capability("provider.load_failure", fatal)
        session.coordinator.hooks.register(
            "llm:request", request_id, name="anchors-request", priority=100
        )
        session.coordinator.hooks.register(
            "tool:pre", guard_delegate, name="anchors-fixed-delegation", priority=1
        )
        if not child:
            session.coordinator.register_capability("session.spawn", self.spawn)

    def prepare_wire(self, session):
        self.verify(session)
        tools = session.coordinator.get("tools")
        schemas = tuple(
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
                "strict": False,
            }
            for t in tools.values()
        )
        self.policies[session.session_id].policy = replace(
            self.policies[session.session_id].policy, wire_tools=schemas
        )

    async def spawn(
        self,
        *,
        agent_name,
        instruction,
        parent_session,
        agent_configs,
        sub_session_id=None,
        provider_preferences=None,
        **kwargs,
    ):
        permitted = (
            agent_name == "anchors:builder"
            and parent_session is self.sessions[0]
            and not self.called
            and provider_preferences is None
            and instruction == TASK_INSTRUCTION
        )
        if not permitted:
            self.protocol_error = True
        require(permitted, "delegate_protocol")
        self.called = True
        resolver = parent_session.coordinator.get_capability("model_role_resolver")
        result = await resolver.resolve(["coding", "general"])
        require(
            result
            and result[0].model == self.worker_model
            and result[0].provider == "openai"
            and result[0].config.get("reasoning_effort") == self.worker_effort,
            "resolved_treatment",
        )
        self.resolution = [r.to_dict() for r in result]
        preferences = result
        output = await self.prepared.spawn(
            self.child_bundle,
            instruction,
            compose=False,
            parent_session=parent_session,
            session_id=sub_session_id,
            provider_preferences=preferences,
            session_cwd=self.workspace,
            before_initialize=self.before_initialize,
            orchestrator_config={"max_iterations": 22},
        )
        self.completed = output.get("status") == "success"
        return output

    async def run(self):
        return await asyncio.wait_for(
            self._run(), self.authority.ledger.limits.whole_cell_s
        )

    async def _run(self):
        require(
            not self.workspace.exists()
            and self.workspace.parent.is_dir()
            and self.matrix_dir.is_dir(),
            "workspace",
        )
        self.sources.validate_runtime()
        stock = await load_anchors(self.sources, self.matrix_dir / "bundle-cache")
        self.matrix = {
            "name": "anchors-eval",
            "description": "bounded Anchors repair",
            "roles": {
                role: {
                    "description": role,
                    "candidates": [
                        {
                            "provider": "openai",
                            "model": self.worker_model,
                            "config": {"reasoning_effort": self.worker_effort},
                        }
                    ],
                }
                for role in ("coding", "general", "fast")
            },
        }
        matrix_file = self.matrix_dir / "anchors-eval.yaml"
        require(not matrix_file.exists(), "matrix_exists")
        matrix_file.write_bytes(canonical(self.matrix))
        stage_task(self.workspace)
        self.child_bundle = profile(
            stock,
            self.sources,
            self.workspace,
            self.matrix_dir,
            model_config(
                self.worker_model,
                self.worker_effort,
                self.authority.ledger.limits.output_max,
                self.authority.timeout_s,
            ),
            True,
        )
        bundle = profile(
            stock,
            self.sources,
            self.workspace,
            self.matrix_dir,
            model_config(
                self.root_model,
                self.root_effort,
                self.authority.ledger.limits.output_max,
                self.authority.timeout_s,
            ),
        )
        self.prepared = await bundle.prepare(
            install_deps=False, strict=True, cache_dir=self.matrix_dir / "module-cache"
        )
        # Enumerate actual stock exports without inventing a miniature delegate.
        root = await self.prepared.create_session(
            session_id=uuid.uuid4().hex,
            session_cwd=self.workspace,
            before_initialize=self.before_initialize,
        )
        self.wire[False] = tuple(root.coordinator.get("tools"))
        self.wire[True] = tuple(WORKER_EXPORTS)
        require("delegate" in self.wire[False], "stock_delegate_missing")
        prompt = (
            "Call delegate exactly once with these exact arguments: "
            + canonical(DELEGATE_ARGUMENTS).decode()
            + ". Do not override model/role or delegate again. Acknowledge completion."
        )
        await root.execute(prompt)
        require(
            self.called
            and self.completed
            and len(self.sessions) == 2
            and not self.protocol_error,
            "journey_incomplete",
        )
        return snapshot_artifact(self.workspace)

    async def close(self):
        okay = True
        for session in reversed(self.sessions):
            try:
                await asyncio.wait_for(session.cleanup(), 15)
            except BaseException:
                okay = False
        for sdk, http, transport in self.clients:
            try:
                await asyncio.wait_for(sdk.close(), 10)
                await asyncio.wait_for(http.aclose(), 10)
                if not transport.closed:
                    await asyncio.wait_for(transport.aclose(), 10)
                okay &= sdk.is_closed() and http.is_closed and transport.closed
            except BaseException:
                okay = False
        return bool(okay)
