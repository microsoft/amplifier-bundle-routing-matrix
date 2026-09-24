# Host provider availability

Hosts that retain unavailable configured accounts can register the synchronous
capability `provider.check_available(instance_id)`. It returns normally for a
usable mounted account and raises an actionable, safe exception otherwise.
Routing checks the exact mounted instance before exact model names or cached
catalogs. A catalog failure also remains a failure. Only the already declared
matrix candidates and ordered roles may supply fallback; exhausted failed
candidates re-raise their first error instead of returning no-match and letting
a caller silently inherit its default account. Hosts without this capability
retain legacy failure handling. Unknown roles, absent providers and model no-matches
still return an empty result; a prior availability/catalog failure is not a
no-match. An accidentally asynchronous callback is a host contract error: routing
rejects its awaitable without trying another account. Hosts must not catch that
error and inherit the default route.

The cache is keyed by mounted account, never the matrix's bare provider family.
Core `instance_id` takes precedence over legacy `id` in mount-plan lookup.
Inherited lifecycle caches now use
`session.routing["preresolved_models_by_instance"]`; the old
`preresolved_models` field is not read or reinterpreted. Old family keys can
collide with an unrelated account ID, so mixed-version sessions may incur one
fresh catalog fetch instead of reusing an ambiguous catalog. Other routing state
is retained. The direct `resolve_model_role(..., preresolved_models=...)` argument
and the resolver's own session cache use mounted account IDs as keys. A host must
not forward an account cache across a change in what that instance ID identifies.

An application that resolves agent roles immediately before each spawn/resume
may explicitly register `routing.defer_agent_resolution=True`. Lifecycle hooks
still publish their usual routing source and restore role pins, but do not query
every unused agent's catalog or rewrite its preferences. The
`model_role_resolver` remains available. This is an application-owned contract:
the host must resolve the requested role and propagate a failure before child
execution; enabling deferral without implementing that boundary is incorrect.
