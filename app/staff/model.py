from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

if TYPE_CHECKING:
    from app.auth.model import User


class Designation(str, enum.Enum):
    receptionist = "receptionist"
    assistant = "assistant"
    nurse = "nurse"
    operator = "operator"


class Staff(Base):
    """A staff member: their own login (user) working for a doctor (doctor)."""

    __tablename__ = "staff"
    __table_args__ = (UniqueConstraint("user_id", name="uq_staff_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # the staff member's own account
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # the doctor this staff member works for
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    designation: Mapped[Designation] = mapped_column(
        Enum(Designation, name="designation"),
        nullable=False,
        server_default="receptionist",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        foreign_keys=[user_id],
        back_populates="staff_profile",
    )
    doctor: Mapped["User"] = relationship(
        foreign_keys=[doctor_id],
        back_populates="staff_members",
    )
