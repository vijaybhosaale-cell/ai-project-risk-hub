"""AI-ready interface.

The prototype ships ONLY a rule-based advisor. No machine-learning model has been
trained and no language model is called. To integrate one later, implement the
``RiskAdvisor`` protocol (e.g. an LLM that drafts explanations, or a model trained
on the company's own historical incidents) and register it in ``get_advisor``.
The rest of the application only talks to this interface.
"""
from __future__ import annotations

import os
from typing import Protocol

from . import engine_risk


class RiskAdvisor(Protocol):
    name: str
    uses_trained_model: bool

    def detect(self, company_id: int) -> list[dict]:
        """Return risk findings: dicts with title, probability, impact, explanation, ..."""

    def explain(self, risk: dict) -> str:
        """Return a human-readable explanation for a stored risk."""


class RuleBasedAdvisor:
    name = "Rule-based engine v1 (explainable, no ML)"
    uses_trained_model = False

    def detect(self, company_id: int) -> list[dict]:
        return engine_risk.detect(company_id)

    def explain(self, risk: dict) -> str:
        return risk.get("explanation") or ""


class ExternalModelAdvisor:
    """Placeholder for a future LLM / ML advisor. Disabled unless configured and implemented."""
    name = "External AI model (not configured)"
    uses_trained_model = True

    def __init__(self, provider: str):
        self.provider = provider

    def detect(self, company_id: int) -> list[dict]:
        raise NotImplementedError("No external AI model is integrated in this prototype.")

    def explain(self, risk: dict) -> str:
        raise NotImplementedError("No external AI model is integrated in this prototype.")


def get_advisor() -> RiskAdvisor:
    # AI_PROVIDER is intentionally ignored until an implementation exists.
    _ = os.environ.get("AI_PROVIDER")
    return RuleBasedAdvisor()
