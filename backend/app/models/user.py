from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.court import Court

from app.database import Base, UTCDateTime


class UserType(enum.StrEnum):
    ATTORNEY = "attorney"
    CLERK = "clerk"
    JUDGE = "judge"
    SELF_REPRESENTED = "self_represented"
    PUBLIC = "public"
    ADMIN = "admin"


class CourtRole(enum.StrEnum):
    FILER = "filer"
    CLERK = "clerk"
    JUDGE = "judge"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    verified_email: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    bar_number: Mapped[str | None] = mapped_column(String(20), index=True)
    bar_number_verified: Mapped[bool] = mapped_column(default=False)
    user_type: Mapped[UserType] = mapped_column(Enum(UserType))
    phone: Mapped[str | None] = mapped_column(String(20))
    firm_name: Mapped[str | None] = mapped_column(String(255))
    keycloak_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    administration_version: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )

    court_roles: Mapped[list[UserCourtRole]] = relationship(back_populates="user")
    favorite_cases: Mapped[list[FavoriteCase]] = relationship(back_populates="user")
    favorite_courts: Mapped[list[FavoriteCourt]] = relationship(back_populates="user")

    __table_args__ = (Index("ix_users_email_lower", func.lower(email)),)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class UserCourtRole(Base):
    __tablename__ = "user_court_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), index=True)
    role: Mapped[CourtRole] = mapped_column(Enum(CourtRole))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="court_roles")

    __table_args__ = (Index("uq_user_court_role", "user_id", "court_id", "role", unique=True),)


class FavoriteCase(Base):
    __tablename__ = "favorite_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "case_id", name="uq_user_case_favorite"),)

    user: Mapped[User] = relationship(back_populates="favorite_cases")
    case: Mapped[Case] = relationship()


class FavoriteCourt(Base):
    __tablename__ = "favorite_courts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), index=True)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "court_id", name="uq_user_court_favorite"),)

    user: Mapped[User] = relationship(back_populates="favorite_courts")
    court: Mapped[Court] = relationship()
