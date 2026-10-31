from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

# Child models only import User under TYPE_CHECKING, so importing them here
# registers them with Base.metadata without a circular import.
from app.addresses.model import Addresses
from app.invitation.model import Invitation
from app.staff.model import Staff


class UserRole(str, enum.Enum):
    doctor = "doctor"
    medical = "medical"
    patient = "patient"
    docbro = "docbro"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    email: Mapped[str | None] = mapped_column(
        String(320),
        unique=True,
        nullable=True,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    phone: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        nullable=True,
        index=True,
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        nullable=False,
        server_default="patient",
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Collections are lazy-loaded; use selectinload() in queries that need them.
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    invitation: Mapped[list["Invitation"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # this user's own staff record (when they are a staff member)
    staff_profile: Mapped["Staff | None"] = relationship(
        foreign_keys="Staff.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )

    # staff members working for this user (when they are a doctor)
    staff_members: Mapped[list["Staff"]] = relationship(
        foreign_keys="Staff.doctor_id",
        back_populates="doctor",
        cascade="all, delete-orphan",
    )

    addresses: Mapped[list["Addresses"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    replaced_by_token_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")
