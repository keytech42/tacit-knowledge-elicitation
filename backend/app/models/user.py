import enum
import uuid

from sqlalchemy import Boolean, Column, Enum as SAEnum, ForeignKey, String, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class UserType(str, enum.Enum):
    HUMAN = "human"
    SERVICE = "service"


class RoleName(str, enum.Enum):
    ADMIN = "admin"
    AUTHOR = "author"
    RESPONDENT = "respondent"
    REVIEWER = "reviewer"


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True),
)


class Role(UUIDMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(SAEnum(RoleName, name="rolename"), unique=True)
    permissions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    user_type: Mapped[str] = mapped_column(SAEnum(UserType, name="usertype"))
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    system_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    roles: Mapped[list[Role]] = relationship(secondary=user_roles, lazy="selectin")
