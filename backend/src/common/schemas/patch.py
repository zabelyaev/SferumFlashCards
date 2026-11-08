from typing import TYPE_CHECKING, ClassVar

from pydantic import model_validator

from common.schemas.base import BaseSchema

if TYPE_CHECKING:
    from typing import Self


class PatchSchema(BaseSchema):
    """Validate partial updates while distinguishing omitted fields from nulls."""

    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        null_fields = sorted(
            field
            for field in self.model_fields_set - self.nullable_fields
            if getattr(self, field) is None
        )
        if null_fields:
            raise ValueError(f"Fields cannot be null: {', '.join(null_fields)}.")
        return self
