from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

if TYPE_CHECKING:
    from app.auth.model import User


class RoleAssign(str, enum.Enum):
    doctor = "doctor"
    medical = "medical"


class Status(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    expired = "expired"


class Invitation(Base):
    __tablename__ = "invitation"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    invite_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)

    # store a hash of the invite token, never the raw token
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    role_to_assign: Mapped[RoleAssign] = mapped_column(
        Enum(RoleAssign, name="role_assign"),
        nullable=False,
        server_default="doctor",
    )

    status: Mapped[Status] = mapped_column(
        Enum(Status, name="invitation_status"),
        nullable=False,
        server_default="pending",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user: Mapped["User"] = relationship(back_populates="invitation")
