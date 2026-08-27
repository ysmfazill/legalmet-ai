"""API request/response schemas (Pydantic, camelCase JSON)."""
from app.schemas.analytics import (
    BatchInspectionOut,
    BatchStats,
    DashboardSummary,
    InspectionStatusBreakdown,
    RecurringViolation,
)
from app.schemas.audit import AuditEventOut, ModelVersionOut
from app.schemas.common import HealthResponse, Message, Paginated
from app.schemas.evidence_graph import EvidenceGraph, EvidenceGraphEdge, EvidenceGraphNode
from app.schemas.finding import EvidenceOut, FindingOut, ReviewActionOut, ReviewFindingRequest
from app.schemas.image import (
    BoundingBox,
    ExtractedFieldOut,
    ImageOut,
    ImageRegionOut,
    RegisterImageRequest,
)
from app.schemas.inspection import (
    AnalyzeInspectionRequest,
    CreateInspectionRequest,
    FindingCounts,
    InspectionDetailOut,
    InspectionSummaryOut,
    PackageOut,
)
from app.schemas.product import ProductOut
from app.schemas.regulatory import (
    RegulationOut,
    RegulationVersionOut,
    RuleApplicabilityOut,
    RuleOut,
)
from app.schemas.user import AuthTokenResponse, LoginRequest, UserOut

__all__ = [
    "AnalyzeInspectionRequest",
    "AuditEventOut",
    "AuthTokenResponse",
    "BatchInspectionOut",
    "BatchStats",
    "BoundingBox",
    "CreateInspectionRequest",
    "DashboardSummary",
    "EvidenceGraph",
    "EvidenceGraphEdge",
    "EvidenceGraphNode",
    "EvidenceOut",
    "ExtractedFieldOut",
    "FindingCounts",
    "FindingOut",
    "HealthResponse",
    "ImageOut",
    "ImageRegionOut",
    "InspectionDetailOut",
    "InspectionStatusBreakdown",
    "InspectionSummaryOut",
    "LoginRequest",
    "Message",
    "ModelVersionOut",
    "PackageOut",
    "Paginated",
    "ProductOut",
    "RecurringViolation",
    "RegisterImageRequest",
    "RegulationOut",
    "RegulationVersionOut",
    "ReviewActionOut",
    "ReviewFindingRequest",
    "RuleApplicabilityOut",
    "RuleOut",
    "UserOut",
]
