"""Pydantic schema base.

All API schemas serialise camelCase JSON (to match the TypeScript frontend and
`@legalmet/types`) while using snake_case field names in Python. Response models
also read directly from ORM objects (`from_attributes`).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
