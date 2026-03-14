"""
Supabase async client factory.

Usage:
    client = await create_supabase_client()
    app.state.supabase = client
"""

import os

from supabase import AsyncClient, acreate_client


async def create_supabase_client() -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return await acreate_client(url, key)
