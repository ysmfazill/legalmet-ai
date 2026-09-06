"""ORM models.

Importing this package registers every table on ``Base.metadata`` (used by
``create_all`` and Alembic autogenerate). The module order below reflects the
Evidence Graph dependency direction.
"""
from app.models.audit import AuditEvent
from app.models.batch import BatchInspection
from app.models.citizen import CitizenReport, CitizenReportEvent, CitizenScan
from app.models.compliance import (
    ComplianceEvaluation,
    ComplianceRule,
    EvaluationFinding,
)
from app.models.extraction import ExtractedField
from app.models.finding import ComplianceFinding, Evidence
from app.models.hitl import (
    FieldCorrection,
    FindingReview,
    FindingReviewEvent,
    InspectionDecision,
)
from app.models.image import Image, ImageRegion
from app.models.inspection import Inspection, Package
from app.models.lot import (
    Lot,
    LotPackage,
    MeasurementEvaluation,
    RegulatoryProcedure,
    SamplingRun,
)
from app.models.model_version import ModelVersion
from app.models.perception import OcrTextResult, ProcessingRun
from app.models.product import Product
from app.models.regulatory import (
    Regulation,
    RegulationVersion,
    RegulatorySource,
    Rule,
    RuleApplicability,
)
from app.models.report import Report, ReportEvidence, ReportVersion
from app.models.review import ReviewAction
from app.models.user import User
from app.models.verification import VerificationResult, VerificationTask

__all__ = [
    "AuditEvent",
    "BatchInspection",
    "CitizenReport",
    "CitizenReportEvent",
    "CitizenScan",
    "ComplianceEvaluation",
    "ComplianceFinding",
    "ComplianceRule",
    "EvaluationFinding",
    "Evidence",
    "ExtractedField",
    "FieldCorrection",
    "FindingReview",
    "FindingReviewEvent",
    "Image",
    "ImageRegion",
    "Inspection",
    "InspectionDecision",
    "Lot",
    "LotPackage",
    "MeasurementEvaluation",
    "ModelVersion",
    "OcrTextResult",
    "Package",
    "ProcessingRun",
    "Product",
    "Regulation",
    "RegulationVersion",
    "RegulatoryProcedure",
    "RegulatorySource",
    "Report",
    "ReportEvidence",
    "ReportVersion",
    "Rule",
    "RuleApplicability",
    "SamplingRun",
    "ReviewAction",
    "User",
    "VerificationResult",
    "VerificationTask",
]
