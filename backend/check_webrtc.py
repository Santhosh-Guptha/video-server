import asyncio
import httpx

async def main():
    url = "http://localhost:8889/INBTEST1001C3_HD/whep"
    async with httpx.AsyncClient() as client:
        try:
            print("Connecting to:", url)
            resp = await client.post(
                url,
                content=b"",
                headers={"Content-Type": "application/sdp"},
                timeout=5.0
            )
            print("Response status:", resp.status_code)
            print("Response body:", resp.text)
        except Exception as e:
            print("Error type:", type(e))
            print("Error message:", str(e))
            print("Error representation:", repr(e))

asyncio.run(main())
