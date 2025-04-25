#!/usr/bin/env python3
import asyncio
from src.db.base import async_session_factory
from src.db.repositories import group_repo

async def check_group():
    async with async_session_factory() as session:
        # Check if group 1 exists
        group = await group_repo.get(session, 1)
        print(f'Group ID 1 exists: {group is not None}')
        if group:
            print(f'Details: {group}')
        
        # List all groups
        from sqlalchemy import select
        from src.db.models import Group
        
        query = select(Group)
        result = await session.execute(query)
        groups = result.scalars().all()
        
        print(f"Found {len(groups)} total groups:")
        for g in groups:
            print(f"Group ID: {g.id}, Name: {g.name}")

if __name__ == "__main__":
    asyncio.run(check_group()) 