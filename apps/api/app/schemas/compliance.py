import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class ComplianceCheckCreate(BaseModel):
    """Formal contract (06-MVP骨架充实与功能闭环计划.md §3.1): `subject_id` +
    `ruleset_id`, `Idempotency-Key` from the request header.

    `company_id` / `rule_codes` / body `idempotency_key` are deprecated
    aliases kept for one dev cycle — the route records which were used in
    the response's `deprecations` list.
    """

    tenant_id: uuid.UUID
    subject_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None  # deprecated alias for subject_id
    evaluation_time: datetime
    ruleset_id: uuid.UUID | None = None
    rule_codes: list[str] | None = None  # deprecated ad-hoc rule list
    idempotency_key: str | None = None  # deprecated; prefer the Idempotency-Key header

    @model_validator(mode="after")
    def _require_subject_and_rules(self) -> "ComplianceCheckCreate":
        if self.subject_id is None and self.company_id is None:
            raise ValueError("subject_id (or deprecated company_id) is required")
        if self.ruleset_id is None and not self.rule_codes:
            raise ValueError("ruleset_id (or deprecated rule_codes) is required")
        return self

    @property
    def resolved_subject_id(self) -> uuid.UUID:
        assert self.subject_id is not None or self.company_id is not None
        return self.subject_id or self.company_id  # type: ignore[return-value]


class PrecheckItemOut(BaseModel):
    rule_code: str
    rule_name: str
    status: str
    missing_facts: list
    applicable_reason: str | None
    excluded_reason: str | None

    @classmethod
    def from_preview(cls, preview) -> "PrecheckItemOut":
        return cls(
            rule_code=preview.rule_code,
            rule_name=preview.rule_name,
            status=preview.status,
            missing_facts=preview.missing_facts,
            applicable_reason=preview.applicable_reason,
            excluded_reason=preview.excluded_reason,
        )


class PrecheckOut(BaseModel):
    items: list[PrecheckItemOut]


class ConclusionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_version_id: uuid.UUID
    rule_code: str
    rule_name: str
    result_status: str
    missing_facts: list
    applicable_reason: str | None
    excluded_reason: str | None

    @classmethod
    def from_conclusion(cls, conclusion) -> "ConclusionOut":
        return cls(
            id=conclusion.id,
            rule_version_id=conclusion.rule_version_id,
            rule_code=conclusion.rule_version.rule.code,
            rule_name=conclusion.rule_version.rule.name,
            result_status=conclusion.result_status,
            missing_facts=conclusion.missing_facts,
            applicable_reason=conclusion.applicable_reason,
            excluded_reason=conclusion.excluded_reason,
        )


class ComplianceCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    subject_id: uuid.UUID
    evaluation_time: datetime
    rule_set_id: uuid.UUID | None
    ruleset_snapshot: list
    status: str
    conclusions: list[ConclusionOut]
    deprecations: list[str] = []

    @classmethod
    def from_check(cls, check, deprecations: list[str] | None = None) -> "ComplianceCheckOut":
        return cls(
            id=check.id,
            tenant_id=check.tenant_id,
            subject_id=check.company_id,
            evaluation_time=check.evaluation_time,
            rule_set_id=check.rule_set_id,
            ruleset_snapshot=check.ruleset_snapshot,
            status=check.status,
            conclusions=[ConclusionOut.from_conclusion(c) for c in check.conclusions],
            deprecations=deprecations or [],
        )


class ProofStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence_no: int
    step_type: str
    rule_version_id: uuid.UUID | None
    rule_id: uuid.UUID | None
    rule_code: str | None
    input_facts: dict
    calculation: dict
    output_state: dict

    @classmethod
    def from_step(cls, step) -> "ProofStepOut":
        return cls(
            sequence_no=step.sequence_no,
            step_type=step.step_type,
            rule_version_id=step.rule_version_id,
            rule_id=step.rule_version.rule_id if step.rule_version else None,
            rule_code=step.rule_version.rule.code if step.rule_version else None,
            input_facts=step.input_facts,
            calculation=step.calculation,
            output_state=step.output_state,
        )


class ProofOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conclusion_id: uuid.UUID
    root_step_id: uuid.UUID | None
    steps: list[ProofStepOut]

    @classmethod
    def from_proof(cls, proof) -> "ProofOut":
        return cls(
            id=proof.id,
            conclusion_id=proof.conclusion_id,
            root_step_id=proof.root_step_id,
            steps=[ProofStepOut.from_step(s) for s in proof.steps],
        )
