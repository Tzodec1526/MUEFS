from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.case import COUNSEL_ROLES, ParticipantRole


class ParticipantChange(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    party_name: str = Field(min_length=1, max_length=255)
    role: ParticipantRole
    account_email: EmailStr | None = None
    attorney_bar_number: str | None = Field(default=None, min_length=1, max_length=20)
    represented_party_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool = True
    access_enabled: bool = False
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_access(self):
        if self.access_enabled and (not self.is_active or not self.account_email):
            raise ValueError("Access requires an active participant and a linked account")
        if self.role not in COUNSEL_ROLES and (
            self.attorney_bar_number or self.represented_party_name
        ):
            raise ValueError("Counsel details require an attorney role")
        return self
