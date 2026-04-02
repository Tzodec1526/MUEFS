from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.user import UserType


class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    bar_number: str | None = None
    user_type: UserType
    phone: str | None = None
    firm_name: str | None = None


class UserCreate(UserBase):
    keycloak_id: str | None = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserProfile(UserResponse):
    full_name: str
