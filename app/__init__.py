import asyncio
import sys
from app.core.dns_fallback import setup_dns_fallback

setup_dns_fallback()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

