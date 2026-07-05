from __future__ import annotations

import pytest

from runtime.engine.pipeline_runner import PhaseTransitionManager, TerminationStatus


class TestPhaseTransitionManager:
    """Unit tests for the conditional ReAct phase routing logic."""

    def test_default_planning_to_execution(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase("planning", {}, 1)
        assert t.next_phase == "execution"
        assert t.safety_override is None

    def test_default_execution_to_observability(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase("execution", {}, 1)
        assert t.next_phase == "observability"

    def test_observability_to_self_correction(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase("observability", {}, 1)
        assert t.next_phase == "self_correction"

    def test_self_correction_complete_goes_to_result(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "self_correction",
            {"result_validation": {"validation_status": "complete"}},
            1,
        )
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.SUCCESS

    def test_self_correction_partial_retry_goes_to_planning(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "self_correction",
            {"result_validation": {"validation_status": "partial", "retry_recommended": True}},
            1,
        )
        assert t.next_phase == "planning"

    def test_self_correction_failed_retry_goes_to_planning(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "self_correction",
            {"result_validation": {"validation_status": "failed", "retry_recommended": True}},
            1,
        )
        assert t.next_phase == "planning"

    def test_self_correction_inconclusive_early_goes_to_execution(self):
        pm = PhaseTransitionManager(max_iterations=10)
        t = pm.next_phase(
            "self_correction",
            {"result_validation": {"validation_status": "inconclusive", "retry_recommended": False}},
            1,
        )
        assert t.next_phase == "execution"

    def test_self_correction_inconclusive_late_escalates(self):
        pm = PhaseTransitionManager(max_iterations=10)
        t = pm.next_phase(
            "self_correction",
            {"result_validation": {"validation_status": "inconclusive", "retry_recommended": False}},
            6,
        )
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.ESCALATED_HUMAN

    def test_planning_escalate_goes_to_result(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "planning",
            {"cost_risk_assessment": {"recommendation": "escalate"}},
            1,
        )
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.ESCALATED_HUMAN

    def test_planning_reduce_scope_goes_to_planning(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "planning",
            {"cost_risk_assessment": {"recommendation": "reduce_scope"}},
            1,
        )
        assert t.next_phase == "planning"

    def test_planning_next_phase_hint(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "planning",
            {"cost_risk_assessment": {"next_phase_hint": "result"}},
            1,
        )
        assert t.next_phase == "result"

    def test_execution_abort_goes_to_result(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "execution",
            {"tool_invocation": {"next_action": "abort"}},
            1,
        )
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.FAILURE

    def test_execution_escalate_goes_to_result(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "execution",
            {"tool_invocation": {"next_action": "escalate"}},
            1,
        )
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.ESCALATED_HUMAN

    def test_execution_guardrail_aborted_goes_to_result(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "execution",
            {"safety_guardrails": {"guardrail_status": "aborted"}},
            1,
        )
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.FAILURE

    def test_execution_guardrail_escalate_to_human(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "execution",
            {"safety_guardrails": {"recommendation": "escalate_to_human"}},
            1,
        )
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.ESCALATED_HUMAN

    def test_execution_resume_with_limits(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "execution",
            {"safety_guardrails": {"recommendation": "resume_with_limits"}},
            1,
        )
        assert t.next_phase == "execution"

    def test_execution_next_phase_hint(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "execution",
            {"tool_invocation": {"next_phase_hint": "observability"}},
            1,
        )
        assert t.next_phase == "observability"

    def test_self_correction_recurse_without_adjusted_plan(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "self_correction",
            {"recursion_or_termination": {"decision": "recurse"}},
            1,
        )
        assert t.next_phase == "planning"

    def test_self_correction_recurse_with_adjusted_plan(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "self_correction",
            {"recursion_or_termination": {"decision": "recurse"}, "adjusted_plan": ["step"]},
            1,
        )
        assert t.next_phase == "execution"

    def test_self_correction_terminate_success(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "self_correction",
            {"recursion_or_termination": {"decision": "terminate_success"}},
            1,
        )
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.SUCCESS

    def test_self_correction_terminate_failure(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "self_correction",
            {"recursion_or_termination": {"decision": "terminate_failure"}},
            1,
        )
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.FAILURE

    def test_self_correction_terminate_partial(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "self_correction",
            {"recursion_or_termination": {"decision": "terminate_partial"}},
            1,
        )
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.PARTIAL

    def test_self_correction_escalate_human(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase(
            "self_correction",
            {"recursion_or_termination": {"decision": "escalate_human"}},
            1,
        )
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.ESCALATED_HUMAN

    def test_self_correction_default_continue(self):
        pm = PhaseTransitionManager(max_iterations=5)
        t = pm.next_phase("self_correction", {}, 2)
        assert t.next_phase == "execution"

    def test_self_correction_max_iterations_reached(self):
        pm = PhaseTransitionManager(max_iterations=5)
        t = pm.next_phase("self_correction", {}, 5)
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.PARTIAL

    def test_unknown_phase_terminates_safely(self):
        pm = PhaseTransitionManager()
        t = pm.next_phase("result", {}, 1)
        assert t.next_phase == "result"

    def test_cycle_detection_forces_result(self):
        pm = PhaseTransitionManager()
        state = {"result_validation": {"validation_status": "inconclusive", "retry_recommended": False}}
        # Force repeated visits to self_correction
        for i in range(1, 5):
            t = pm.next_phase("self_correction", state, i)
        assert t.next_phase == "result"
        assert t.safety_override == TerminationStatus.PARTIAL

    def test_self_correction_next_phase_hint(self):
        pm = PhaseTransitionManager()
        # Hint applies when no table rule overrides it.
        t = pm.next_phase(
            "self_correction",
            {"result_validation": {"next_phase_hint": "planning"}},
            1,
        )
        assert t.next_phase == "planning"

    def test_dotted_and_fallback_key_resolution(self):
        pm = PhaseTransitionManager()
        # Dotted key should win
        t1 = pm.next_phase(
            "execution",
            {"tool_invocation": {"next_action": "abort"}},
            1,
        )
        assert t1.next_phase == "result"
        # Fallback key should also work
        t2 = pm.next_phase(
            "execution",
            {"execution": {"next_action": "abort"}},
            1,
        )
        assert t2.next_phase == "result"
