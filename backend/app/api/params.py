from typing import Annotated

from fastapi import Path, Query

from app.schemas.common import MAX_RECORD_ID

RecordId = Annotated[int, Path(ge=1, le=MAX_RECORD_ID)]
Page = Annotated[int, Query(ge=1, le=MAX_RECORD_ID)]
