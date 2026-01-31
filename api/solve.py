import os
import time
from typing import Optional
from dataclasses import dataclass
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright, Playwright

app = FastAPI()

BROWSERLESS_TOKEN = os.environ.get("BROWSERLESS_TOKEN")
if not BROWSERLESS_TOKEN:
    raise Exception("Set BROWSERLESS_TOKEN in Vercel environment variables")

# ================= DATA ==================
@dataclass
class TurnstileResult:
    turnstile_value: Optional[str]
    elapsed_time_seconds: float
    status: str
    reason: Optional[str] = None

# ================= SOLVER =================
class TurnstileSolver:

    def __init__(self, debug=False):
        self.debug = debug

    def _debug(self, msg):
        if self.debug:
            print(f"[DEBUG] {msg}")

    async def _wait_for_turnstile(self, page, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            try:
                token = await page.evaluate(
                    """() => {
                        const el = document.querySelector(
                            'input[name="cf-turnstile-response"]'
                        );
                        return el ? el.value : null;
                    }"""
                )
                if token and len(token) > 20:
                    return token
            except:
                pass
            await page.wait_for_timeout(300)
        return None

    async def solve(self, url: str):
        start = time.time()
        try:
            # Connect to Browserless Cloud
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(
                    f"wss://chrome.browserless.io?token={BROWSERLESS_TOKEN}"
                )
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 900}
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                self._debug("Page loaded, waiting for Turnstile...")
                token = await self._wait_for_turnstile(page)
                elapsed = round(time.time() - start, 3)
                await browser.close()
                if not token:
                    return TurnstileResult(
                        None, elapsed, "failure", "Turnstile token not detected"
                    )
                return TurnstileResult(token, elapsed, "success")
        except Exception as e:
            return TurnstileResult(None, round(time.time() - start, 3), "error", str(e))

# ================= API ENDPOINT =================
@app.get("/solve")
async def solve_turnstile(request: Request):
    url = request.query_params.get("url")
    sitekey = request.query_params.get("sitekey")  # legacy

    if not url:
        return JSONResponse({"error": "Missing 'url' parameter"}, status_code=400)

    url = unquote(url)

    solver = TurnstileSolver(debug=True)
    result = await solver.solve(url)

    return JSONResponse(result.__dict__)
