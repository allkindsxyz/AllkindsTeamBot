from sqlalchemy import select, exists, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Group, GroupMember, MemberRole
from src.db.repositories.base import BaseRepository

class GroupRepository(BaseRepository[Group]):
    """Repository for working with Group models."""
    
    def __init__(self):
        super().__init__(Group)
    
    async def get(self, session: AsyncSession, group_id: int) -> Group | None:
        """Get a group by ID."""
        query = select(Group).where(Group.id == group_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    async def exists(self, session: AsyncSession, group_id: int) -> bool:
        """Check if a group exists by ID."""
        query = select(exists().where(Group.id == group_id))
        result = await session.execute(query)
        return result.scalar_one()
    
    async def create(self, session: AsyncSession, data: dict) -> Group:
        """Create a new group."""
        group = Group(**data)
        session.add(group)
        await session.commit()
        await session.refresh(group)
        return group
        
    async def get_user_groups(self, session: AsyncSession, user_id: int) -> list[Group]:
        """Get all groups a user belongs to (including as creator or member)."""
        # First, get groups where user is creator
        creator_query = select(Group).where(
            Group.creator_id == user_id,
            Group.is_active == True  # Only get active groups
        )
        creator_result = await session.execute(creator_query)
        creator_groups = creator_result.scalars().all()
        
        # Then, get groups where user is a member
        member_query = select(Group).join(
            GroupMember, Group.id == GroupMember.group_id
        ).where(
            GroupMember.user_id == user_id,
            Group.is_active == True  # Only get active groups
        )
        member_result = await session.execute(member_query)
        member_groups = member_result.scalars().all()
        
        # Combine results, removing duplicates
        all_groups = list(set(creator_groups) | set(member_groups))
        return all_groups
        
    async def add_user_to_group(
        self, 
        session: AsyncSession, 
        user_id: int, 
        group_id: int, 
        role: str = MemberRole.MEMBER
    ) -> GroupMember:
        """Add a user as a member of a group."""
        # Check if already a member
        query = select(GroupMember).where(
            (GroupMember.user_id == user_id) & 
            (GroupMember.group_id == group_id)
        )
        result = await session.execute(query)
        existing_membership = result.scalar_one_or_none()
        
        if existing_membership:
            # Already a member, just return existing membership
            return existing_membership
            
        # Create new membership
        membership = GroupMember(
            user_id=user_id,
            group_id=group_id,
            role=role
        )
        session.add(membership)
        await session.commit()
        await session.refresh(membership)
        return membership

    async def get_group_members(self, session: AsyncSession, group_id: int) -> list[GroupMember]:
        """Get all members of a group."""
        query = select(GroupMember).where(GroupMember.group_id == group_id)
        result = await session.execute(query)
        return result.scalars().all()

    async def remove_user_from_group(self, session: AsyncSession, user_id: int, group_id: int) -> bool:
        """Remove a user from a group."""
        query = delete(GroupMember).where(
            GroupMember.user_id == user_id,
            GroupMember.group_id == group_id
        )
        result = await session.execute(query)
        await session.commit()
        return result.rowcount > 0
        
    async def is_user_in_group(self, session: AsyncSession, user_id: int, group_id: int) -> bool:
        """Check if a user is a member of a group."""
        query = select(exists().where(
            (GroupMember.user_id == user_id) & 
            (GroupMember.group_id == group_id)
        ))
        result = await session.execute(query)
        return result.scalar_one()
        
    async def is_group_creator(self, session: AsyncSession, user_id: int, group_id: int) -> bool:
        """Check if a user is the creator of a group."""
        query = select(exists().where(
            (Group.id == group_id) & 
            (Group.creator_id == user_id)
        ))
        result = await session.execute(query)
        return result.scalar_one()
        
    async def get_user_role(self, session: AsyncSession, user_id: int, group_id: int) -> str | None:
        """Get the role of a user in a group. Returns None if user is not in group."""
        query = select(GroupMember.role).where(
            (GroupMember.user_id == user_id) & 
            (GroupMember.group_id == group_id)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def get_group_member(self, session: AsyncSession, user_id: int, group_id: int) -> GroupMember:
        """
        Get a GroupMember by user_id and group_id.
        
        Args:
            session: Database session
            user_id: ID of the user
            group_id: ID of the group
            
        Returns:
            The GroupMember object or None if not found
        """
        try:
            query = select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            from loguru import logger
            logger.error(f"Error in get_group_member: {e}")
            return None
    
    async def set_member_profile(self, session: AsyncSession, user_id: int, group_id: int, nickname: str, photo_file_id: str | None = None) -> GroupMember:
        """Set or update a group member's profile (nickname and photo)."""
        # Get the member
        member = await self.get_group_member(session, user_id, group_id)
        
        if not member:
            raise ValueError(f"User {user_id} is not a member of group {group_id}")
        
        # Update member profile directly on the object
        member.nickname = nickname
        member.photo_file_id = photo_file_id
        
        # Commit the changes
        await session.commit()
        
        # Refresh the member object
        await session.refresh(member)
        return member
        
    async def get_member_count(self, session: AsyncSession, group_id: int) -> int:
        """Get the number of members in a group."""
        from sqlalchemy import func
        query = select(func.count()).where(GroupMember.group_id == group_id)
        result = await session.execute(query)
        return result.scalar_one() or 0
        
    async def get_question_count(self, session: AsyncSession, group_id: int) -> int:
        """Get the number of questions in a group."""
        from sqlalchemy import func
        from src.db.models import Question
        query = select(func.count()).where(Question.group_id == group_id)
        result = await session.execute(query)
        return result.scalar_one() or 0

    async def get_by_invite_code(self, session: AsyncSession, invite_code: str) -> Group | None:
        """Get a group by its invite code."""
        query = select(Group).where(Group.invite_code == invite_code)
        result = await session.execute(query)
        return result.scalar_one_or_none()

# Create a singleton instance
group_repo = GroupRepository() 