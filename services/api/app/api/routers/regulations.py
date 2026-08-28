"""Regulatory intelligence routes (Prompts 1 + 5).

Read endpoints expose the Source → Document → Version → Requirement hierarchy
with full provenance. Writes are limited to an ADMIN-only, audited
verification-status change on sources — ordinary inspectors can never alter
authoritative regulatory data.

Scope guardrail: nothing here evaluates compliance. The strongest statement
these routes make about a perceived field is "candidate requirement —
applicability not evaluated, awaiting the compliance engine".
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_current_user, get_services_dep, pagination, require_role
from app.core.enums import CandidateMappingStatus, UserRole
from app.db.session import get_db
from app.models import Rule, User
from app.schemas.common import Paginated
from app.schemas.regulatory import (
    CandidateRequirementOut,
    FieldCandidateOut,
    FieldCandidatesOut,
    PaginatedRequirements,
    RegulationOut,
    RegulatoryDocumentOut,
    RegulatoryRequirementDetailOut,
    RegulatoryRequirementOut,
    RegulatorySourceOut,
    RegulatorySourceUpdateIn,
    RegulatoryVersionOut,
    RequirementProvenanceOut,
    RuleOut,
    VersionSelectionOut,
)
from app.services.registry import Services
from app.services.rules.validators import registered_validators

router = APIRouter(tags=["regulatory"])

# Regulatory reads: any authenticated user. Source verification changes: the
# elevated role that owns authoritative-data lifecycle decisions.
_REGULATORY_ADMIN = (UserRole.ADMIN,)


@router.get("/regulations/sources", response_model=list[RegulatorySourceOut])
def list_sources(
    verification_status: str | None = Query(None, alias="verificationStatus"),
    source_type: str | None = Query(None, alias="sourceType"),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[RegulatorySourceOut]:
    sources = services.regulatory.list_sources(
        db, verification_status=verification_status, source_type=source_type
    )
    return [RegulatorySourceOut.model_validate(s) for s in sources]


@router.get("/regulations/sources/{source_id}", response_model=RegulatorySourceOut)
def get_source(
    source_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> RegulatorySourceOut:
    return RegulatorySourceOut.model_validate(services.regulatory.get_source(db, source_id))


@router.patch("/regulations/sources/{source_id}", response_model=RegulatorySourceOut)
def update_source_verification(
    source_id: UUID,
    body: RegulatorySourceUpdateIn,
    user: User = Depends(require_role(*_REGULATORY_ADMIN)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> RegulatorySourceOut:
    """ADMIN-only, audited verification-state change (before/after recorded)."""
    source = services.regulatory.update_source_verification(
        db,
        source_id=source_id,
        verification_status=body.verification_status.value,
        verification_note=body.verification_note,
        actor_id=user.id,
    )
    return RegulatorySourceOut.model_validate(source)


@router.get("/regulations/documents", response_model=list[RegulatoryDocumentOut])
def list_documents(
    source_id: UUID | None = Query(None, alias="sourceId"),
    document_type: str | None = Query(None, alias="documentType"),
    is_demo: bool | None = Query(None, alias="isDemo"),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[RegulatoryDocumentOut]:
    documents = services.regulatory.list_documents(
        db, source_id=source_id, document_type=document_type, is_demo=is_demo
    )
    return [RegulatoryDocumentOut.model_validate(d) for d in documents]


@router.get("/regulations/documents/{document_id}", response_model=RegulatoryDocumentOut)
def get_document(
    document_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> RegulatoryDocumentOut:
    return RegulatoryDocumentOut.model_validate(
        services.regulatory.get_document(db, document_id)
    )


@router.get("/regulations/versions", response_model=list[RegulatoryVersionOut])
def list_versions(
    document_id: UUID | None = Query(None, alias="documentId"),
    status: str | None = Query(None),
    effective_on: datetime | None = Query(None, alias="effectiveOn"),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[RegulatoryVersionOut]:
    versions = services.regulatory.list_versions(
        db, document_id=document_id, status=status, effective_on=effective_on
    )
    return [RegulatoryVersionOut.model_validate(v) for v in versions]


@router.get("/regulations/versions/resolve", response_model=VersionSelectionOut)
def resolve_version(
    document_id: UUID = Query(..., alias="documentId"),
    on: datetime = Query(...),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> VersionSelectionOut:
    """Deterministic effective-date selection. NO_APPLICABLE_VERSION is an
    explicit state — the resolver never silently falls back to the newest."""
    version, selection = services.regulatory.resolve_version(
        db, document_id=document_id, at=on
    )
    return VersionSelectionOut(
        document_id=document_id,
        requested_date=on,
        status=selection,
        version=RegulatoryVersionOut.model_validate(version) if version else None,
    )


@router.get("/regulations/requirements", response_model=PaginatedRequirements)
def list_requirements(
    pg: Pagination = Depends(pagination),
    version_id: UUID | None = Query(None, alias="versionId"),
    document_id: UUID | None = Query(None, alias="documentId"),
    source_id: UUID | None = Query(None, alias="sourceId"),
    field_key: str | None = Query(None, alias="fieldKey"),
    requirement_type: str | None = Query(None, alias="requirementType"),
    category: str | None = Query(None),
    status: str | None = Query(None),
    effective_on: datetime | None = Query(None, alias="effectiveOn"),
    current: bool | None = Query(None),
    is_demo: bool | None = Query(None, alias="isDemo"),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> PaginatedRequirements:
    rows, total = services.regulatory.list_requirements(
        db,
        version_id=version_id,
        document_id=document_id,
        source_id=source_id,
        field_key=field_key,
        requirement_type=requirement_type,
        category=category,
        status=status,
        effective_on=effective_on,
        current=current,
        is_demo=is_demo,
        limit=pg.limit,
        offset=pg.offset,
    )
    return PaginatedRequirements(
        items=[RegulatoryRequirementOut.model_validate(_to_out(r)) for r in rows],
        total=total,
        page=pg.page,
        page_size=pg.page_size,
    )


@router.get(
    "/regulations/requirements/{requirement_id}",
    response_model=RegulatoryRequirementDetailOut,
)
def get_requirement(
    requirement_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> RegulatoryRequirementDetailOut:
    rule, version, document, source = services.regulatory.get_requirement(db, requirement_id)
    base = _to_out(rule)
    return RegulatoryRequirementDetailOut(
        **base,
        provenance=RequirementProvenanceOut(
            authority=document.authority,
            document_title=document.title,
            document_identifier=document.document_identifier,
            version_label=version.version_label,
            effective_from=version.effective_from,
            effective_to=version.effective_until,
            source_reference=rule.source_reference,
            requirement_reference=rule.rule_code,
            source_name=source.name if source else None,
            source_verification_status=(
                source.verification_status if source else None
            ),
            canonical_url=document.official_source_url,
        ),
        version=RegulatoryVersionOut.model_validate(version),
    )


# --- Candidate mapping (Prompt 5, Phase 8): perception → regulations ---------


@router.get(
    "/inspections/{inspection_id}/regulatory-candidates",
    response_model=FieldCandidatesOut,
)
def get_field_candidates(
    inspection_id: UUID,
    on: datetime | None = Query(None),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> FieldCandidatesOut:
    """Map detected perception fields to CANDIDATE requirement definitions.

    Never a compliance verdict: every mapping is marked applicability-not-
    -evaluated and awaiting the compliance engine.
    """
    result = services.regulatory.field_candidates(db, inspection_id=inspection_id, on=on)
    fields: list[FieldCandidateOut] = []
    for entry in result["fields"]:
        field = entry["field"]
        candidates = [
            CandidateRequirementOut(
                requirement_id=rule.id,
                rule_code=rule.rule_code,
                title=rule.title,
                source_reference=rule.source_reference,
                version_label=version.version_label,
                effective_from=version.effective_from,
                source_verification_status=source.verification_status if source else None,
            )
            for rule, version, document, source in entry["candidates"]
        ]
        fields.append(
            FieldCandidateOut(
                field_id=field.id,
                field_type=field.field_type,
                field_value=field.normalized_value or field.raw_text,
                field_status=field.status,
                candidates=candidates,
                mapping_status=CandidateMappingStatus(entry["mapping_status"]),
                applicability_status=CandidateMappingStatus(entry["applicability_status"]),
                evaluation_status=CandidateMappingStatus(entry["evaluation_status"]),
            )
        )
    return FieldCandidatesOut(
        inspection_id=inspection_id,
        context_date=result["context_date"],
        fields=fields,
    )


# --- Prompt 1 (demo rule flow) — unchanged -----------------------------------


@router.get("/regulations", response_model=list[RegulationOut])
def list_regulations(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[RegulationOut]:
    regulations = services.regulatory.list_regulations(db)
    return [RegulationOut.model_validate(r) for r in regulations]


@router.get("/rules/validators", response_model=list[str])
def list_validators(_user: User = Depends(get_current_user)) -> list[str]:
    # The deterministic validators available to rules (structural, not legal).
    return registered_validators()


@router.get("/rules", response_model=Paginated[RuleOut])
def list_rules(
    pg: Pagination = Depends(pagination),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> Paginated[RuleOut]:
    rules, total = services.regulatory.list_rules(db, limit=pg.limit, offset=pg.offset)
    return Paginated(
        items=[RuleOut.model_validate(r) for r in rules],
        total=total,
        page=pg.page,
        page_size=pg.page_size,
    )


def _to_out(rule: Rule) -> dict:
    return {
        "id": rule.id,
        "version_id": rule.regulation_version_id,
        "rule_code": rule.rule_code,
        "title": rule.title,
        "description": rule.requirement_summary,
        "requirement_type": rule.requirement_type,
        "field_key": rule.field_key,
        "expected_format": rule.expected_format,
        "mandatory": rule.mandatory,
        "applicability_definition": rule.applicability_definition or {},
        "source_reference": rule.source_reference,
        "status": rule.status,
        "is_demo": rule.is_demo,
        "created_at": rule.created_at,
    }
