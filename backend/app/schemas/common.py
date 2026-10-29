"""Bounds shared by request schemas and endpoint parameters."""

from typing import Annotated

from pydantic import Field

# Record ids and optimistic-concurrency versions are PostgreSQL INTEGER columns. A larger
# value can match no row, and the database driver rejects it with an error, not a miss.
MAX_RECORD_ID = 2_147_483_647

RecordId = Annotated[int, Field(ge=1, le=MAX_RECORD_ID)]
ExpectedVersion = Annotated[int, Field(ge=0, le=MAX_RECORD_ID)]
