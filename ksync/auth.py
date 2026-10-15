import asyncio
from fastcore.utils import *
from fastcdp import CDP

NOTEBOOK = 'https://read.amazon.com/notebook'
REAUTH_CMD = 'ksync-auth'
_SIGNED_IN = r"location.host=='read.amazon.com'"

async def kindle_page(
    reauth=False, # Wait for a manual sign-in in the browser when the session has expired? (Else raise)
    timeout=300, # Seconds to wait for that sign-in
):
    "A tab on fastcdp's persistent Chrome profile, signed in to the Kindle notebook; Amazon redirects to its sign-in form otherwise"
    page = await (await CDP.launch()).new_page()
    await page.goto(NOTEBOOK)
    if await page.eval(_SIGNED_IN): return page
    if not reauth: raise RuntimeError(f'Kindle session expired; run `{REAUTH_CMD}` to sign in again')
    print('Sign in to Amazon in the Chrome window')
    await page.wait_for(_SIGNED_IN, timeout=timeout)
    return page

def auth():
    "Open the browser for a manual Kindle sign-in; the session stays in the Chrome profile for later syncs"
    asyncio.run(kindle_page(reauth=True))
    print('Signed in')
