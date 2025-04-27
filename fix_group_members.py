#!/usr/bin/env python3
import asyncio
import sys
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_session
from src.db.models import Group, GroupMember, User

async def fix_group_members_table():
    """Fix inconsistencies in group_members table where user_id doesn't match the expected creator_id."""
    print("Starting group_members table fix...")
    
    # Get all users to verify
    users = {}
    groups = {}
    group_members = []
    
    async for session in get_session():
        try:
            # Load all users for reference
            user_query = select(User)
            user_result = await session.execute(user_query)
            all_users = user_result.scalars().all()
            users = {user.id: user for user in all_users}
            print(f"Loaded {len(users)} users")
            
            # Load all groups
            group_query = select(Group)
            group_result = await session.execute(group_query)
            all_groups = group_result.scalars().all()
            groups = {group.id: group for group in all_groups}
            print(f"Loaded {len(groups)} groups")
            
            # Load all group members
            member_query = select(GroupMember)
            member_result = await session.execute(member_query)
            group_members = member_result.scalars().all()
            print(f"Loaded {len(group_members)} group members")
            
            # Check for inconsistencies in group members
            issues_found = False
            for member in group_members:
                group = groups.get(member.group_id)
                if not group:
                    print(f"WARNING: Member {member.id} references non-existent group {member.group_id}")
                    continue
                
                if member.role == "creator" and member.user_id != group.creator_id:
                    issues_found = True
                    print(f"Found inconsistency: GroupMember {member.id} has role 'creator' but user_id {member.user_id} != group.creator_id {group.creator_id}")
                    
                    # Fix the issue by updating the member's user_id to match the group's creator_id
                    update_query = update(GroupMember).where(
                        (GroupMember.id == member.id)
                    ).values(
                        user_id=group.creator_id
                    )
                    await session.execute(update_query)
                    print(f"Fixed: Updated member.user_id from {member.user_id} to {group.creator_id}")
            
            if not issues_found:
                print("No inconsistencies found in group_members table.")
            else:
                await session.commit()
                print("Changes committed to database.")
            
            return True
        
        except Exception as e:
            print(f"Error while fixing group_members table: {e}")
            await session.rollback()
            return False

if __name__ == "__main__":
    result = asyncio.run(fix_group_members_table())
    sys.exit(0 if result else 1) 