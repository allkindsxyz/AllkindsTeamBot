from sqlalchemy import select, exists, delete
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
        creator_query = select(Group).where(Group.creator_id == user_id)
        creator_result = await session.execute(creator_query)
        creator_groups = creator_result.scalars().all()
        
        # Then, get groups where user is a member
        member_query = select(Group).join(
            GroupMember, Group.id == GroupMember.group_id
        ).where(
            GroupMember.user_id == user_id
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

# Create a singleton instance
group_repo = GroupRepository() 