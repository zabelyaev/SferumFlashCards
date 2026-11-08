import math
from typing import TYPE_CHECKING

from common.schemas.text import validate_postgres_text

if TYPE_CHECKING:
    from pydantic import JsonValue


MAX_JSON_NESTING_DEPTH = 253


def validate_postgres_json(value: JsonValue) -> None:
    """Reject values unsafe for JSONB storage or subsequent profile responses."""
    pending: list[tuple[JsonValue, int]] = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if isinstance(item, str):
            validate_postgres_text(item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("JSON numbers must be finite.")
        elif isinstance(item, (list, dict)):
            if depth > MAX_JSON_NESTING_DEPTH:
                raise ValueError(
                    "JSON values must not exceed "
                    f"{MAX_JSON_NESTING_DEPTH} nested containers."
                )
            if isinstance(item, dict):
                for key in item:
                    validate_postgres_text(key)
                pending.extend((child, depth + 1) for child in item.values())
            else:
                pending.extend((child, depth + 1) for child in item)
