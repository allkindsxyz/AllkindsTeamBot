from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class MemberRole(str, Enum):
    """Enum for group member roles."""
    CREATOR = "creator"
    ADMIN = "admin"
    MEMBER = "member"


class GroupMember(Base):
    """GroupMember model for user membership in groups."""

    __tablename__ = "group_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    
    # Member role within the group
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MemberRole.MEMBER,
    )
    
    # Onboarding profile data
    nickname: Mapped[str] = mapped_column(String(32), nullable=True)
    photo_file_id: Mapped[str] = mapped_column(String(255), nullable=True)
    
    # Timestamps
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_memberships")
    
    def __repr__(self) -> str:
        return f"<GroupMember {self.id}: {self.user_id} in {self.group_id} as {self.role}>" 