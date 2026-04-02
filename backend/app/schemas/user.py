from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserType


class UserBase(BaseModel):
    email: EmailStr
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    bar_number: str | None = Field(None, max_length=20)
    user_type: UserType
    phone: str | None = Field(None, max_length=20)
    firm_name: str | None = Field(None, max_length=255)


class UserCreate(UserBase):
    keycloak_id: str | None = Field(None, max_length=255)


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserProfile(UserResponse):
    full_name: str
