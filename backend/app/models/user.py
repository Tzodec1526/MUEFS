import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserType(str, enum.Enum):
    ATTORNEY = "attorney"
    CLERK = "clerk"
    JUDGE = "judge"
    SELF_REPRESENTED = "self_represented"
    ADMIN = "admin"


class CourtRole(str, enum.Enum):
    FILER = "filer"
    CLERK = "clerk"
    JUDGE = "judge"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    bar_number: Mapped[str | None] = mapped_column(String(20), index=True)
    user_type: Mapped[UserType] = mapped_column(Enum(UserType))
    phone: Mapped[str | None] = mapped_column(String(20))
    firm_name: Mapped[str | None] = mapped_column(String(255))
    keycloak_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    court_roles: Mapped[list["UserCourtRole"]] = relationship(back_populates="user")
    favorite_cases: Mapped[list["FavoriteCase"]] = relationship(back_populates="user")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class UserCourtRole(Base):
    __tablename__ = "user_court_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), index=True)
    role: Mapped[CourtRole] = mapped_column(Enum(CourtRole))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="court_roles")


class FavoriteCase(Base):
    __tablename__ = "favorite_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "case_id", name="uq_user_case_favorite"),
    )

    user: Mapped["User"] = relationship(back_populates="favorite_cases")
