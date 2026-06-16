import asyncio
from urllib.parse import urlparse

from .settings import settings


async def main():
    from playwright.async_api import async_playwright
    settings.prepare()
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            str(settings.internal_browser_profile), headless=False, channel="chrome"
        )
        ata = await context.new_page()
        await ata.goto(settings.ata_base_url)
        yunzhidao = await context.new_page()
        await yunzhidao.goto(settings.yunzhidao_base_url)
        print("Browser opened. Please complete SSO login in both tabs.")
        print("After login, come back here and press Enter to save session.")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, input, "Press Enter when done: ")
        await context.storage_state(path=str(settings.internal_auth_state))
        print(f"Session saved to {settings.internal_auth_state}")
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
