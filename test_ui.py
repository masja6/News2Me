import asyncio
from fastapi import Request
from newstome.ui import admin
async def main():
    try:
        response = admin(Request({"type": "http", "method": "GET"}), "dummy")
        # To render it, we can just await the response body
        await response(scope={"type": "http"}, receive=None, send=lambda message: None)
    except Exception as e:
        import traceback
        traceback.print_exc()
asyncio.run(main())
