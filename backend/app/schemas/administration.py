from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.user import CourtRole, UserType
from app.schemas.common import ExpectedVersion


class AccountChange(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    user_type: UserType
    keycloak_id: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool = True
    bar_number: str | None = Field(default=None, min_length=1, max_length=20)
    bar_number_verified: bool = False
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def verified_bar_requires_number(self):
        if self.bar_number_verified and (
            not self.bar_number or self.user_type != UserType.ATTORNEY
        ):
            raise ValueError("Bar verification requires an attorney account and a bar number")
        return self


class AccountUpdate(AccountChange):
    expected_version: ExpectedVersion


class CourtRoleChange(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    role: Literal[CourtRole.CLERK, CourtRole.JUDGE, CourtRole.ADMIN]
    action: Literal["grant", "revoke"]
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: ExpectedVersion
