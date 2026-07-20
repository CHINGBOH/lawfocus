from dataclasses import dataclass, field

from app.domain.truth import TruthValue


@dataclass
class ProofStepData:
    step_type: str
    calculation: dict
    input_facts: dict = field(default_factory=dict)
    output_state: dict = field(default_factory=dict)


@dataclass
class RuleResult:
    rule_code: str
    status: TruthValue
    missing_facts: list[str] = field(default_factory=list)
    applicable_reason: str | None = None
    excluded_reason: str | None = None
    variable_bindings: dict = field(default_factory=dict)
    proof_steps: list[ProofStepData] = field(default_factory=list)
