from __future__ import annotations

import asyncio
import importlib.util
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..contracts.agent_spec import AgentSpec
from ..contracts.message import Message, MessageType
from .agent_loader import AgentLoader
from .llm_engine import EvaluationEngine, LLMEngine, LLMResponse
from .message_bus import MessageBus
from .state_manager import StateManager

# Optional MCP integration
try:
    from mcp_servers.bootstrap import create_registry
    from mcp_servers.gateway import MCPGateway
    from mcp_servers.registry import MCPRegistry as _MCPRegistry
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

# Optional Figma integration
def _load_figma_config_module():
    """Load figma-agent-core/config.py without requiring a valid Python package name."""
    core_dir = Path(__file__).resolve().parent.parent.parent / "figma-agent-core"
    config_path = core_dir / "config.py"
    if not config_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("figma_config", str(config_path))
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_figma_config_mod = _load_figma_config_module()
HAS_FIGMA_CONFIG = _figma_config_mod is not None


class TerminationStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    ESCALATED_HUMAN = "escalated_human"


class PipelineStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"


@dataclass
class PhaseTransition:
    next_phase: str
    reason: str
    safety_override: TerminationStatus | None = None


class PhaseTransitionManager:
    """Routes the ReAct loop between phases based on agent outputs.

    Default sequence: planning → execution → observability → self_correction → result.
    Agent outputs can override the next phase (e.g., skip replanning, escalate to result).
    """

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self._phase_history: list[str] = []

    def next_phase(self, current_phase: str, state: dict[str, Any], iteration: int) -> PhaseTransition:
        """Decide the next ReAct phase and optional safety override."""
        self._phase_history.append(current_phase)

        # Cycle detection: if a phase repeats too often, force termination
        if self._phase_history.count(current_phase) > 3:
            return PhaseTransition(
                next_phase="result",
                reason=f"Phase '{current_phase}' visited 4 times — possible loop",
                safety_override=TerminationStatus.PARTIAL,
            )

        if current_phase == "planning":
            return self._from_planning(state)
        if current_phase == "execution":
            return self._from_execution(state)
        if current_phase == "observability":
            return PhaseTransition(next_phase="self_correction", reason="Observation complete; proceed to validation")
        if current_phase == "self_correction":
            return self._from_self_correction(state, iteration)

        return PhaseTransition(next_phase="result", reason="Unknown phase — terminating safely")

    def _from_planning(self, state: dict[str, Any]) -> PhaseTransition:
        recommendation = self._get(state, "cost_risk_assessment.recommendation", "cost_risk_assessment", "recommendation")
        if recommendation == "escalate":
            return PhaseTransition(
                next_phase="result",
                reason="Cost/risk assessment recommends escalation",
                safety_override=TerminationStatus.ESCALATED_HUMAN,
            )
        if recommendation == "reduce_scope":
            return PhaseTransition(next_phase="planning", reason="Scope reduced; replan before execution")
        hint = self._get(state, "cost_risk_assessment.next_phase_hint")
        if hint in ("execution", "planning", "result"):
            return PhaseTransition(next_phase=hint, reason="Explicit next_phase_hint from cost_risk_assessment")
        return PhaseTransition(next_phase="execution", reason="Planning complete; proceed to execution")

    def _from_execution(self, state: dict[str, Any]) -> PhaseTransition:
        next_action = self._get(state, "execution.next_action", "tool_invocation", "next_action")
        if next_action == "abort":
            return PhaseTransition(
                next_phase="result",
                reason="Tool invocation aborted",
                safety_override=TerminationStatus.FAILURE,
            )
        if next_action == "escalate":
            return PhaseTransition(
                next_phase="result",
                reason="Tool invocation requires escalation",
                safety_override=TerminationStatus.ESCALATED_HUMAN,
            )

        guardrail_status = self._get(state, "execution.guardrail_status", "safety_guardrails", "guardrail_status")
        if guardrail_status == "aborted":
            return PhaseTransition(
                next_phase="result",
                reason="Safety guardrails aborted execution",
                safety_override=TerminationStatus.FAILURE,
            )

        recommendation = self._get(state, "execution.recommendation", "safety_guardrails", "recommendation")
        if recommendation == "escalate_to_human":
            return PhaseTransition(
                next_phase="result",
                reason="Safety guardrails requested human escalation",
                safety_override=TerminationStatus.ESCALATED_HUMAN,
            )
        if recommendation == "resume_with_limits":
            return PhaseTransition(next_phase="execution", reason="Resume execution with adjusted limits")

        hint = self._get(state, "execution.next_phase_hint")
        if hint in ("observability", "execution", "result"):
            return PhaseTransition(next_phase=hint, reason="Explicit next_phase_hint from execution")
        return PhaseTransition(next_phase="observability", reason="Execution complete; proceed to observation")

    def _from_self_correction(self, state: dict[str, Any], iteration: int) -> PhaseTransition:
        validation_status = self._get(state, "validation.validation_status", "result_validation", "validation_status")
        retry_recommended = self._get(state, "validation.retry_recommended", "result_validation", "retry_recommended")
        decision = self._get(state, "validation.decision", "recursion_or_termination", "decision")

        # First honor the explicit recursion/termination decision if present
        if decision == "terminate_success":
            return PhaseTransition(
                next_phase="result",
                reason="Termination decision: success",
                safety_override=TerminationStatus.SUCCESS,
            )
        if decision == "terminate_failure":
            return PhaseTransition(
                next_phase="result",
                reason="Termination decision: failure",
                safety_override=TerminationStatus.FAILURE,
            )
        if decision == "terminate_partial":
            return PhaseTransition(
                next_phase="result",
                reason="Termination decision: partial",
                safety_override=TerminationStatus.PARTIAL,
            )
        if decision == "escalate_human":
            return PhaseTransition(
                next_phase="result",
                reason="Termination decision: escalate to human",
                safety_override=TerminationStatus.ESCALATED_HUMAN,
            )
        if decision == "recurse":
            adjusted_plan = state.get("adjusted_plan")
            if adjusted_plan:
                return PhaseTransition(next_phase="execution", reason="Recurse with adjusted plan")
            return PhaseTransition(next_phase="planning", reason="Recurse without adjusted plan — replan")

        # Then evaluate validation status
        if validation_status == "complete":
            return PhaseTransition(
                next_phase="result",
                reason="Validation complete",
                safety_override=TerminationStatus.SUCCESS,
            )
        if validation_status in ("partial", "failed") and retry_recommended:
            return PhaseTransition(next_phase="planning", reason=f"Validation={validation_status}; retry recommended")
        if validation_status == "inconclusive":
            if iteration < self.max_iterations / 2:
                return PhaseTransition(next_phase="execution", reason="Inconclusive early — gather more data")
            return PhaseTransition(
                next_phase="result",
                reason="Inconclusive late — escalate",
                safety_override=TerminationStatus.ESCALATED_HUMAN,
            )

        hint = self._get(state, "validation.next_phase_hint", "result_validation", "next_phase_hint")
        if hint in ("self_correction", "execution", "planning", "result"):
            return PhaseTransition(next_phase=hint, reason="Explicit next_phase_hint from validation")

        # Default: if we still have budget, try one more execution; otherwise result partial
        if iteration < self.max_iterations:
            return PhaseTransition(next_phase="execution", reason="Default continue to execution")
        return PhaseTransition(
            next_phase="result",
            reason="Max iterations reached",
            safety_override=TerminationStatus.PARTIAL,
        )

    @staticmethod
    def _get(state: dict[str, Any], dotted_key: str, *fallback_keys: str) -> Any:
        """Resolve a value from the state dict.

        Tries the dotted path first, then treats fallback_keys as an alternate
        dotted path under each common prefix (e.g. ``tool_invocation.next_action``).
        """

        def _resolve(obj: Any, path: list[str]) -> Any:
            for k in path:
                if isinstance(obj, dict):
                    obj = obj.get(k)
                else:
                    return None
            return obj

        value = _resolve(state, dotted_key.split("."))
        if value is not None:
            return value

        if fallback_keys:
            fallback_path = ".".join(str(k) for k in fallback_keys).split(".")
            for prefix in ["", "execution", "validation"]:
                root = state.get(prefix, {}) if prefix else state
                value = _resolve(root, fallback_path)
                if value is not None:
                    return value

        return None


@dataclass
class IterationTrace:
    iteration: int
    phase: str
    agent_path: str
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None
    latency_ms: float
    success: bool
    error: str | None = None


@dataclass
class SessionMetrics:
    session_id: str
    iterations: int = 0
    tools_used: list[str] = field(default_factory=list)
    time_elapsed_ms: float = 0
    tokens_consumed: int = 0
    safety_checks_passed: int = 0
    safety_checks_failed: int = 0


@dataclass
class PipelineResult:
    final_response: str
    termination_status: TerminationStatus
    session_metrics: SessionMetrics
    audit_anchor: str
    trace: list[IterationTrace] = field(default_factory=list)


class PipelineRunner:
    FLOW_SEQUENCE = [
        "tooll_subagents/user/request.md",
        "tooll_subagents/user/context.md",
        "safety-control/input_sanitizer.md",
        "safety-control/threat_detector.md",
        "control/scope_manager.md",
        "tooll_subagents/planning/task_decomposition.md",
        "tooll_subagents/planning/tool_plan_selection.md",
    ]

    SAFETY_AGENTS = [
        "safety-control/input_sanitizer.md",
        "safety-control/threat_detector.md",
        "safety-control/permission_checker.md",
        "control/scope_manager.md",
        "control/policy_enforcer.md",
    ]

    MUTUAL_CHECK_AGENTS = [
        "safety-control/mutual_check/consistency_checker.md",
        "safety-control/mutual_check/result_validator.md",
        "safety-control/mutual_check/quality_assessor.md",
    ]

    def __init__(self, loader: AgentLoader, llm: LLMEngine, bus: MessageBus, state: StateManager,
                 workspace_root: str = ".", max_workers: int = 4, max_iterations: int = 5):
        self.loader = loader
        self.llm = llm
        self.bus = bus
        self.state = state
        self.workspace = workspace_root
        self._max_iterations = max_iterations
        self._agent_cache: dict[str, AgentSpec] = {}
        rules_data = self._load_project_rules()
        self._project_rules = {k: rules_data[k] for k in ("source", "content_hash", "sections")} if rules_data else None
        self._system_context = rules_data.get("system_context") if rules_data else None
        self._evaluator = EvaluationEngine(llm.config) if llm.config.use_evaluator else None

        self._mcp_gateway = None
        if HAS_MCP:
            try:
                registry = create_registry(workspace_root, eager=False)
                self._mcp_gateway = MCPGateway(registry)
            except Exception:
                pass

    def _load_project_rules(self) -> dict[str, Any] | None:
        """Load lightweight project rules and CLAUDE.md from workspace root."""
        rules_path = Path(self.workspace) / "project_rules.md"
        claude_path = Path(self.workspace) / "CLAUDE.md"
        rules_text = rules_path.read_text(encoding="utf-8") if rules_path.exists() else ""
        claude_text = claude_path.read_text(encoding="utf-8") if claude_path.exists() else ""
        if not rules_text and not claude_text:
            return None
        try:
            sections = self._parse_project_rules(rules_text) if rules_text else {}
            project_summary = self._summarize_markdown(rules_text)
            claude_summary = self._summarize_markdown(claude_text)
            return {
                "source": str(rules_path) if rules_path.exists() else None,
                "content_hash": hash(rules_text) & 0xFFFFFFFF if rules_text else 0,
                "sections": sections,
                "claude_md_source": str(claude_path) if claude_path.exists() else None,
                "claude_md_content_hash": hash(claude_text) & 0xFFFFFFFF if claude_text else 0,
                "project_rules_summary": project_summary,
                "claude_md_summary": claude_summary,
                "system_context": self._build_system_context(project_summary, claude_summary),
            }
        except Exception:
            return None

    @staticmethod
    def _parse_project_rules(text: str) -> dict[str, list[str]]:
        """Parse project_rules.md into sections."""
        sections: dict[str, list[str]] = {}
        current: str | None = None
        for line in text.splitlines():
            if line.startswith("# "):
                continue
            if line.startswith("## "):
                current = line[3:].strip()
                sections[current] = []
            elif current and line.strip():
                sections[current].append(line.strip())
        return sections

    @staticmethod
    def _summarize_markdown(text: str, max_chars: int = 2400) -> str:
        """Compress markdown to headings, lists, tables, and short directives."""
        if not text:
            return ""
        kept: list[str] = []
        in_code_fence = False
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line:
                continue
            stripped = line.lstrip()
            if stripped.startswith("```"):
                in_code_fence = not in_code_fence
                continue
            if in_code_fence or raw.startswith("  "):
                kept.append(line)
                continue
            if stripped.startswith(("# ", "## ", "### ", "#### ", "- ", "* ", "| ")):
                kept.append(line)
                continue
            if re.match(r"^\d+\.\s", stripped):
                kept.append(line)
                continue
            if len(stripped) <= 120 and any(marker in stripped for marker in ("—", "→", ":", "|", "must", "always", "never", "Gate", "Rules", "Conventions", "Safety", "Scope")):
                kept.append(line)
                continue
        summary = "\n".join(kept)
        if len(summary) > max_chars:
            summary = summary[:max_chars].rsplit("\n", 1)[0] + "\n..."
        return summary

    @staticmethod
    def _build_system_context(project_summary: str, claude_summary: str, max_total_chars: int = 4000) -> str:
        """Assemble the summarized project rules and CLAUDE.md into one system block."""
        parts = [
            "# Project System Context\n",
            "The following project-wide rules and CLAUDE.md directives are mandatory for every agent in this session.",
        ]
        if project_summary:
            parts.append("\n## Project Rules\n" + project_summary)
        if claude_summary:
            parts.append("\n## CLAUDE.md Directives\n" + claude_summary)
        context = "\n".join(parts)
        if len(context) > max_total_chars:
            context = context[:max_total_chars].rsplit("\n", 1)[0] + "\n..."
        return context

    def _system_context_for_phase(self, phase: str) -> str | None:
        """Return the shared system context for phases that must obey project-wide rules."""
        if phase not in ("planning", "execution"):
            return None
        return self._system_context

    @property
    def mcp_enabled(self) -> bool:
        return self._mcp_gateway is not None and self.llm.config.mcp_enabled

    @property
    def figma_available(self) -> bool:
        """True when figma-agent-core is present and Figma credentials are configured."""
        if not self.mcp_enabled:
            return False
        if not HAS_FIGMA_CONFIG or _figma_config_mod is None:
            return False
        core_dir = Path(self.workspace) / "figma-agent-core"
        if not core_dir.exists():
            return False
        return _figma_config_mod.is_figma_configured()

    async def execute_mcp_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool via MCP servers directly — bypasses LLM for actual I/O operations."""
        if not self._mcp_gateway:
            return {"error": "MCP not available", "is_error": True}

        result = await self._mcp_gateway.execute(tool_name, arguments)
        return {"tool": tool_name, "result": result, "mcp_executed": True}

    def get_mcp_categories(self) -> list[str]:
        """Return MCP category metadata without loading servers.

        Filters out the Figma category if Figma is not configured so the planner
        does not waste tokens on tools that cannot execute.
        """
        if not self.mcp_enabled:
            return []
        categories = self._mcp_gateway.categories()
        if "figma" in categories and not self.figma_available:
            categories = [c for c in categories if c != "figma"]
        return categories

    async def run(self, user_input: str, session_id: str | None = None,
                  max_iterations: int = 5) -> PipelineResult:
        self._max_iterations = max_iterations
        session_id = session_id or uuid.uuid4().hex
        t_start = time.perf_counter()
        self._t_start = t_start
        metrics = SessionMetrics(session_id=session_id)
        trace: list[IterationTrace] = []
        audit_anchor = uuid.uuid4().hex

        await self.bus.start()

        try:
            self.state.create(f"session:{session_id}", {
                "user_input": user_input,
                "status": PipelineStatus.RUNNING.value,
                "started_at": t_start,
            }, scope="session")

            await self._publish_progress("phase.start", {"phase": "session_init", "session_id": session_id})

            # Phase 1: Safety pre-check
            safety_passed = await self._run_safety_pre_check(user_input, session_id, trace, metrics)
            if not safety_passed:
                return PipelineResult(
                    final_response="Request blocked by safety pre-check.",
                    termination_status=TerminationStatus.ESCALATED_HUMAN,
                    session_metrics=metrics,
                    audit_anchor=audit_anchor,
                    trace=trace,
                )

            await self._publish_progress("phase.end", {"phase": "safety_pre_check", "session_id": session_id})

            # Phase 2: Design intake & optional full-pipeline short-circuit
            await self._publish_progress("phase.start", {"phase": "design_intake", "session_id": session_id})
            design_descriptor = await self._run_design_intake(user_input, session_id, trace, metrics)
            await self._publish_progress("phase.end", {"phase": "design_intake", "session_id": session_id})

            if design_descriptor:
                output_mode = design_descriptor.get("output_mode", "both")
                if output_mode in ("full_code", "both"):
                    pipeline_result = await self._run_design_pipeline(design_descriptor, session_id)
                    if pipeline_result and not pipeline_result.get("is_error"):
                        final_response = self._format_design_pipeline_result(design_descriptor, pipeline_result)
                        await self._run_safety_post_check(final_response, session_id, trace, metrics)
                        await self._run_mutual_check(final_response, session_id, trace, metrics)
                        metrics.time_elapsed_ms = (time.perf_counter() - t_start) * 1000
                        self.state.update(f"session:{session_id}", {
                            "status": PipelineStatus.COMPLETED.value,
                            "completed_at": time.time(),
                        }, scope="session")
                        return await self._finalize_and_return(
                            user_input, final_response, TerminationStatus.SUCCESS,
                            metrics, audit_anchor, trace, session_id,
                        )

            # Phase 3: Plan
            await self._publish_progress("phase.start", {"phase": "planning", "session_id": session_id})
            plan = await self._run_planning(user_input, session_id, trace, metrics,
                                            design_descriptor=design_descriptor)
            await self._publish_progress("phase.end", {"phase": "planning", "session_id": session_id})

            # Phase 3: ReAct loop with conditional edges
            transition_manager = PhaseTransitionManager(max_iterations=max_iterations)
            state: dict[str, Any] = {
                "plan": plan,
                "user_input": user_input,
                "session_id": session_id,
                "iteration": 0,
            }
            current_phase = "execution"
            result_text = ""

            while current_phase != "result":
                # Handle replanning requests from conditional edges
                if current_phase == "planning":
                    await self._publish_progress("phase.start", {"phase": "planning", "session_id": session_id})
                    plan = await self._run_planning(user_input, session_id, trace, metrics)
                    state["plan"] = plan
                    await self._publish_progress("phase.end", {"phase": "planning", "session_id": session_id})
                    # After replanning, always move to execution unless overridden
                    current_phase = "execution"
                    continue

                if current_phase == "execution":
                    state["iteration"] += 1
                    metrics.iterations = state["iteration"]

                if state["iteration"] > max_iterations:
                    return await self._finalize_and_return(
                        user_input, result_text or "Max iterations reached.",
                        TerminationStatus.PARTIAL, metrics, audit_anchor, trace, session_id,
                    )

                await self._publish_progress("phase.start", {"phase": current_phase, "session_id": session_id})
                await self._run_phase(current_phase, state, trace, metrics)
                await self._publish_progress("phase.end", {"phase": current_phase, "session_id": session_id})

                transition = transition_manager.next_phase(current_phase, state, state["iteration"])

                # Safety override: hard-terminate to result with a specific status
                if transition.safety_override:
                    return await self._finalize_and_return(
                        user_input,
                        state.get("result", transition.reason),
                        transition.safety_override,
                        metrics, audit_anchor, trace, session_id,
                    )

                # Preserve result text if we are about to finish successfully
                if transition.next_phase == "result":
                    result_text = state.get("result", state.get("observation", {}).get("result", transition.reason))

                current_phase = transition.next_phase

            # Phase 4: Safety post-check
            await self._run_safety_post_check(result_text, session_id, trace, metrics)

            # Phase 5: Final mutual check
            await self._run_mutual_check(result_text, session_id, trace, metrics)

            metrics.time_elapsed_ms = (time.perf_counter() - t_start) * 1000
            self.state.update(f"session:{session_id}", {
                "status": PipelineStatus.COMPLETED.value,
                "completed_at": time.time(),
            }, scope="session")

            return await self._finalize_and_return(
                user_input, result_text, TerminationStatus.SUCCESS,
                metrics, audit_anchor, trace, session_id,
            )

        except Exception as e:
            metrics.time_elapsed_ms = (time.perf_counter() - t_start) * 1000
            return await self._finalize_and_return(
                user_input, f"Pipeline failed: {e}", TerminationStatus.FAILURE,
                metrics, audit_anchor, trace, session_id,
            )
        finally:
            await self.bus.stop()

    async def _finalize_and_return(self, user_input: str, final_response: str,
                                   termination_status: TerminationStatus,
                                   metrics: SessionMetrics, audit_anchor: str,
                                   trace: list[IterationTrace], session_id: str) -> PipelineResult:
        if metrics.time_elapsed_ms <= 0:
            metrics.time_elapsed_ms = (time.perf_counter() - self._t_start) * 1000
        return PipelineResult(
            final_response=final_response,
            termination_status=termination_status,
            session_metrics=metrics,
            audit_anchor=audit_anchor,
            trace=trace,
        )

    async def _run_safety_pre_check(self, user_input: str, session_id: str,
                                    trace: list[IterationTrace], metrics: SessionMetrics) -> bool:
        context: dict[str, Any] = {
            "raw_user_input": user_input,
            "session_id": session_id,
            "project_rules": self._project_rules,
        }

        for agent_path in self.SAFETY_AGENTS:
            result = await self._invoke_agent(agent_path, context, trace, "safety_pre_check", metrics)
            if result and result.parsed:
                blocked = result.parsed.get("blocked", result.parsed.get("status") == "blocked")
                if blocked:
                    metrics.safety_checks_failed += 1
                    return False
                metrics.safety_checks_passed += 1
                context.update(result.parsed)
        return True

    async def _run_design_intake(self, user_input: str, session_id: str,
                                 trace: list[IterationTrace], metrics: SessionMetrics) -> dict[str, Any] | None:
        """Classify request via design_intake.md and return design_descriptor if design project."""
        if not self.mcp_enabled or not self.figma_available:
            return None
        result = await self._invoke_agent(
            "tooll_subagents/user/design_intake.md",
            {
                "raw_request": user_input,
                "source_channel": "cli",
                "session_id": session_id,
                "priority_hint": "normal",
                "project_rules": self._project_rules,
            },
            trace, "design_intake", metrics,
        )
        if not result or not result.parsed:
            return None
        if result.parsed.get("request_type") != "design_project":
            return None
        return result.parsed.get("design_descriptor")

    async def _run_design_pipeline(self, design_descriptor: dict[str, Any],
                                   session_id: str) -> dict[str, Any]:
        """Trigger the full Figma-to-code pipeline via MCP figma_run_pipeline."""
        source_value = design_descriptor.get("source_value", "")
        backend_spec = design_descriptor.get("backend_spec") or {}
        image_enrichment = design_descriptor.get("image_enrichment") or {}
        args: dict[str, Any] = {
            "output_name": session_id[:8],
            "dry_run": False,
            "figma_url": source_value if design_descriptor.get("design_source") == "figma_url" else "",
        }
        file_key = self._extract_figma_file_key(source_value)
        if file_key:
            args["file_key"] = file_key
        if design_descriptor.get("target_scope") == "single_section":
            node_id = self._extract_figma_node_id(source_value)
            if node_id:
                args["node_id"] = node_id
        if backend_spec:
            spec_type = backend_spec.get("spec_type")
            spec_path = backend_spec.get("spec_path", "")
            if spec_type == "openapi":
                args["openapi"] = spec_path
            elif spec_type == "prisma":
                args["prisma"] = spec_path
            else:
                args["backend_spec_text"] = spec_path
        if image_enrichment.get("enabled"):
            args["enable_image_enrichment"] = True
            args["image_provider"] = image_enrichment.get("provider", "unsplash")
            if image_enrichment.get("api_key"):
                args["image_provider_api_key"] = image_enrichment["api_key"]
            if image_enrichment.get("output_dir"):
                args["image_enrichment_output_dir"] = image_enrichment["output_dir"]
            if image_enrichment.get("max_images"):
                args["image_enrichment_max_images"] = image_enrichment["max_images"]
        return await self.execute_mcp_tool("figma_run_pipeline", args)

    def _extract_figma_file_key(self, source_value: str) -> str:
        import re
        match = re.search(r"figma\.com/(?:file|design)/([a-zA-Z0-9_-]+)", source_value)
        return match.group(1) if match else ""

    def _extract_figma_node_id(self, source_value: str) -> str:
        import re
        match = re.search(r"node-id=([0-9-:]+)", source_value)
        return match.group(1).replace("-", ":") if match else ""

    def _get_agent(self, path: str) -> AgentSpec:
        if path not in self._agent_cache:
            self._agent_cache[path] = self.loader.load_agent(path)
        return self._agent_cache[path]

    def _format_design_pipeline_result(self, design_descriptor: dict[str, Any],
                                       pipeline_result: dict[str, Any]) -> str:
        source = design_descriptor.get("source_value", "")
        mode = design_descriptor.get("output_mode", "full_code")
        result = pipeline_result.get("result", pipeline_result)
        status = result.get("status", "unknown")
        summary = f"Design pipeline triggered for {source} (mode={mode}).\nStatus: {status}.\n"
        if result.get("returncode") is not None:
            summary += f"Return code: {result['returncode']}.\n"
        if result.get("stdout"):
            summary += f"\nOutput:\n{result['stdout'][:2000]}"
        if result.get("stderr"):
            summary += f"\nErrors:\n{result['stderr'][:1000]}"
        return summary

    async def _run_planning(self, user_input: str, session_id: str,
                            trace: list[IterationTrace], metrics: SessionMetrics,
                            design_descriptor: dict[str, Any] | None = None) -> dict[str, Any]:
        plan = {
            "user_input": user_input,
            "session_id": session_id,
            "project_rules": self._project_rules,
            "mcp_categories": self.get_mcp_categories() if self.mcp_enabled else [],
            "design_descriptor": design_descriptor,
        }
        for agent_path in self.FLOW_SEQUENCE:
            result = await self._invoke_agent(agent_path, plan, trace, "planning", metrics)
            if result and result.parsed:
                plan.update(result.parsed)
        return plan


    async def _run_phase(self, phase: str, state: dict[str, Any],
                         trace: list[IterationTrace], metrics: SessionMetrics) -> None:
        """Execute one ReAct phase and store results in the shared state."""
        if phase == "execution":
            await self._run_execution(state, trace, metrics)
        elif phase == "observability":
            await self._run_observation(state, trace, metrics)
        elif phase == "self_correction":
            await self._run_validation(state, trace, metrics)
            await self._run_termination_decision(state, trace, metrics)

    async def _run_execution(self, state: dict[str, Any],
                             trace: list[IterationTrace],
                             metrics: SessionMetrics) -> None:
        exec_agents = [
            "tooll_subagents/execution/tool_invocation.md",
            "tooll_subagents/execution/safety_guardrails.md",
        ]
        result: dict[str, Any] = {
            "plan": state.get("plan"),
            "user_input": state.get("user_input"),
            "iteration": state.get("iteration"),
            "session_id": state.get("session_id"),
            "mcp_categories": self.get_mcp_categories() if self.mcp_enabled else [],
        }
        for agent_path in exec_agents:
            llm_result = await self._invoke_agent(agent_path, result, trace, "execution", metrics)
            if llm_result and llm_result.parsed:
                result.update(llm_result.parsed)

        # If the planner selected a Figma MCP tool, execute it directly here.
        tool_call = result.get("tool_call") or result.get("tool")
        if isinstance(tool_call, dict) and tool_call.get("name", "").startswith("figma_"):
            tool_output = await self.execute_mcp_tool(
                tool_call["name"], tool_call.get("arguments", {})
            )
            result["tool_output"] = tool_output
            result["tool_result"] = tool_output.get("result")
            result["success"] = not tool_output.get("result", {}).get("is_error", False)
            if "result" in tool_output.get("result", {}):
                result["result"] = tool_output["result"]["result"]

        state["execution"] = result
        if "result" in result:
            state["result"] = result["result"]

    async def _run_observation(self, state: dict[str, Any],
                               trace: list[IterationTrace],
                               metrics: SessionMetrics) -> None:
        obs_agents = [
            "tooll_subagents/observability/environment_result.md",
            "tooll_subagents/observability/runtime_output.md",
        ]
        exec_result = state.get("execution", {})
        result: dict[str, Any] = dict(exec_result)
        for agent_path in obs_agents:
            llm_result = await self._invoke_agent(agent_path, result, trace, "observation", metrics)
            if llm_result and llm_result.parsed:
                result.update(llm_result.parsed)
        state["observation"] = result
        if "result" in result:
            state["result"] = result["result"]

    async def _run_validation(self, state: dict[str, Any],
                              trace: list[IterationTrace], metrics: SessionMetrics) -> None:
        observation = state.get("observation", {})

        # Fast /goal evaluator: cheap critic checks whether the evidence satisfies the goal.
        goal_evaluation: dict[str, Any] | None = None
        if self._evaluator:
            try:
                evaluator_response = await self._evaluator.evaluate(
                    goal=state.get("user_input", ""),
                    artifacts=observation,
                    criteria=state.get("plan", {}).get("success_criteria"),
                )
                goal_evaluation = {
                    "verdict": {
                        "pass": evaluator_response.pass_,
                        "reason": evaluator_response.reason,
                        "confidence": evaluator_response.confidence,
                    },
                    "criteria_checklist": evaluator_response.criteria_checklist,
                }
            except Exception as e:
                goal_evaluation = {
                    "verdict": {"pass": False, "reason": f"Evaluator error: {e}", "confidence": 0.0},
                    "criteria_checklist": [],
                }

        result = await self._invoke_agent(
            "tooll_subagents/self_correction/result_validation.md",
            {
                "observation": observation,
                "original_request": state.get("user_input"),
                "goal_evaluation": goal_evaluation,
                "iteration_count": state.get("iteration", 0),
                "max_iterations": self._max_iterations,
            },
            trace, "validation", metrics,
        )
        validation: dict[str, Any] = dict(observation)
        if result and result.parsed:
            validation.update(result.parsed)
        validation["goal_evaluation"] = goal_evaluation
        state["validation"] = validation
        if "result" in validation:
            state["result"] = validation["result"]

    async def _run_termination_decision(self, state: dict[str, Any],
                                        trace: list[IterationTrace],
                                        metrics: SessionMetrics) -> None:
        validation = state.get("validation", {})
        result = await self._invoke_agent(
            "tooll_subagents/self_correction/recursion_or_termination.md",
            {"validation": validation, "iteration": state.get("iteration", 1), "max_iterations": self._max_iterations},
            trace, "self_correction", metrics,
        )
        if result and result.parsed:
            validation["decision"] = result.parsed.get("decision", result.parsed.get("next_action", "terminate_success"))
            if "next_phase_hint" in result.parsed:
                validation["next_phase_hint"] = result.parsed["next_phase_hint"]
            if "adjusted_plan" in result.parsed:
                state["adjusted_plan"] = result.parsed["adjusted_plan"]
        else:
            validation["decision"] = "terminate_success"
        state["validation"] = validation

    async def _run_safety_post_check(self, result_text: str, session_id: str,
                                     trace: list[IterationTrace], metrics: SessionMetrics):
        for agent_path in [
            "safety-control/output_reviewer.md",
            "safety-control/data_leak_preventer.md",
            "safety-control/content_checker.md",
        ]:
            await self._invoke_agent(agent_path, {"output": result_text}, trace, "safety_post_check", metrics)

    async def _run_mutual_check(self, result_text: str, session_id: str,
                                trace: list[IterationTrace], metrics: SessionMetrics):
        for agent_path in self.MUTUAL_CHECK_AGENTS:
            await self._invoke_agent(agent_path, {"result": result_text, "session_id": session_id},
                                     trace, "mutual_check", metrics)

    async def _invoke_agent(self, agent_path: str, inputs: dict[str, Any],
                            trace: list[IterationTrace], phase: str,
                            metrics: SessionMetrics | None = None) -> LLMResponse | None:
        t0 = time.perf_counter()

        extra_context = self._system_context_for_phase(phase)
        try:
            spec = self._get_agent(agent_path)
            result = await self.llm.execute(spec, inputs, extra_context=extra_context)
            latency = (time.perf_counter() - t0) * 1000
            trace.append(IterationTrace(
                iteration=len([t for t in trace if t.phase == phase]) + 1,
                phase=phase,
                agent_path=agent_path,
                inputs=inputs,
                outputs=result.parsed,
                latency_ms=latency,
                success=True,
            ))
            session_id = inputs.get("session_id", "")
            iteration = inputs.get("iteration", metrics.iterations if metrics else 0)
            await self._publish_progress("agent.invoke", {
                "iteration": iteration, "phase": phase, "agent_path": agent_path,
                "session_id": session_id, "latency_ms": round(latency, 2), "success": True,
            })
            return result
        except Exception as e:
            latency = (time.perf_counter() - t0) * 1000
            trace.append(IterationTrace(
                iteration=len([t for t in trace if t.phase == phase]) + 1,
                phase=phase,
                agent_path=agent_path,
                inputs=inputs,
                outputs=None,
                latency_ms=latency,
                success=False,
                error=str(e),
            ))
            session_id = inputs.get("session_id", "")
            iteration = inputs.get("iteration", metrics.iterations if metrics else 0)
            await self._publish_progress("agent.invoke", {
                "iteration": iteration, "phase": phase, "agent_path": agent_path,
                "session_id": session_id, "latency_ms": round(latency, 2), "success": False,
            })
            return None

    async def _publish_progress(self, event_type: str, payload: dict[str, Any]):
        """Publish progress event for TUI and external observers."""
        msg = Message(
            message_type=MessageType.EVENT,
            topic=event_type,
            payload=payload,
            sender="pipeline_runner",
        )
        try:
            await self.bus.publish(msg)
        except Exception:
            pass
