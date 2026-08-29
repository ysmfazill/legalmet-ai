"""ORM models.

Importing this package registers every table on ``Base.metadata`` (used by
``create_all`` and Alembic autogenerate). The module order below reflects the
Evidence Graph dependency direction.
"""
from app.models.audit import AuditEvent
from app.models.batch import BatchInspection
from app.models.compliance import (
    ComplianceEvaluation,
    ComplianceRule,
    EvaluationFinding,
)
from app.models.extraction import ExtractedField
from app.models.finding import ComplianceFinding, Evidence
from app.models.image import Image, ImageRegion
from app.models.inspection import Inspection, Package
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
from app.models.review import ReviewAction
from app.models.user import User

__all__ = [
    "AuditEvent",
    "BatchInspection",
    "ComplianceEvaluation",
    "ComplianceFinding",
    "ComplianceRule",
    "EvaluationFinding",
    "Evidence",
    "ExtractedField",
    "Image",
    "ImageRegion",
    "Inspection",
    "ModelVersion",
    "OcrTextResult",
    "Package",
    "ProcessingRun",
    "Product",
    "Regulation",
    "RegulationVersion",
    "RegulatorySource",
    "Rule",
    "RuleApplicability",
    "ReviewAction",
    "User",
]
