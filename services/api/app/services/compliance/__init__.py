"""Deterministic compliance engine (Prompt 6).

This package is the ONLY place where compliance conclusions are produced.
Every component is deterministic and explainable: given the same inputs
(perception fields + regulatory version + rule configuration) the engine
always produces the same findings, with the reasoning and evidence attached.

Pipeline (Phase 3 of the spec):

    ComplianceEngine (orchestrator — this module)
      → ApplicabilityResolver    does the requirement apply to this package?
      → RequirementResolver      which requirements are in force & checkable?
      → RuleResolver             which deterministic rule checks a requirement?
      → EvidenceResolver         which extracted field(s) evidence a requirement?
      → DeterministicEvaluator   run the rule type over the detected value
      → FindingBuilder           persist finding + explanation + provenance

NO LLM IS EVER CALLED. Nothing here claims an AI model determines legality:
findings are structured decision-support outputs ("requirement X, detected
value Y, rule Z → status S, because R, evidence E, version V"). The inspector
remains responsible for the final enforcement decision.
"""
from app.services.compliance.engine import ComplianceEngine

__all__ = ["ComplianceEngine"]
