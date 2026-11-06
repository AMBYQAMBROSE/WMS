from pydantic import BaseModel, Field


class ExpectedVersion(BaseModel):
    """Optimistic locking for edits: send back the row_version you loaded"""

    row_version: int | None = Field(
        default=None,
        description=(
            "The row_version of the record as you loaded it. If someone changed the record since, the save is refused "
            "with 409 instead of silently overwriting their change. Omit to save without the check."
        ),
    )
