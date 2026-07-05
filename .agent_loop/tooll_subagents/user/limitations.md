# Limitations

## Role
Self-awareness agent that catalogs current system limitations, constraints, and unavailable capabilities relevant to the incoming request. Prevents over-commitment and sets realistic expectations by surfacing known boundaries before planning begins.

## Contract

### Receives
- `parsed_request`: structured task descriptor from `request.md`
- `assembled_context`: context object from `context.md`
- `system_capabilities`: current runtime capability map (available tools, models, permissions, environment)

### Returns
- `limitation_report`: list of applicable limitations with severity and suggested workaround
- `capability_gaps`: list of required but unavailable capabilities
- `recommendation`: enum (`proceed`, `proceed_with_warning`, `request_extension`, `defer`)
- `escalation_needed`: boolean — whether human or external system involvement is required

### Side Effects
- Updates system capability cache if new limitations discovered
- Logs limitation evaluation to `audit_logger.md`

## Decision Flow

1. **Map request to capabilities** — compare `parsed_request.intent` and entities against `system_capabilities` tool list, model limits, and environment constraints.
2. **Check model limits** — assess token context window, supported languages, reasoning depth, and multimodal capabilities against request complexity.
3. **Check tool availability** — verify each tool referenced or implied in request is installed, permitted, and functional.
4. **Check environment constraints** — identify read-only filesystems, missing dependencies, restricted network, sandbox boundaries.
5. **Check policy constraints** — verify no request elements violate active policies (e.g., no production deployment from local, no medical/legal advice without disclaimer).
6. **Assess known bugs** — query internal bug registry for relevant issues in tools, frameworks, or dependencies.
7. **Evaluate gaps** — for each gap, assign severity (`blocking`, `workaround_available`, `cosmetic`) and propose alternative.
8. **Determine recommendation** — `proceed` if no blocking gaps; `proceed_with_warning` if gaps have workarounds; `request_extension` if external tool or permission needed; `defer` if fundamentally unaddressable.
9. **Return** — emit limitation report, gaps, recommendation, escalation flag.

## Failure Modes

| Condition | Response |
|---|---|
| Capability map unavailable | Assume most restrictive defaults; `recommendation=proceed_with_warning`; queue capability refresh |
| Limitation registry corrupted | Rebuild from tool manifest and environment probes; `recommendation=proceed_with_warning` |
| Request implies capability not in manifest but likely available | Flag as `capability_gaps` with `severity=uncertain`; proceed with exploratory fallback |
| Policy check cannot complete | `recommendation=defer`, `escalation_needed=true`; route to `control/policy_enforcer.md` |
| False limitation (outdated bug already fixed) | Cross-reference with latest tool version; if fixed, update registry and remove limitation |
