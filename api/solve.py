import os
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright

app = FastAPI()

# ================= ENV =================
BROWSERLESS_TOKEN = os.environ.get("BROWSERLESS_TOKEN")
if not BROWSERLESS_TOKEN:
    raise RuntimeError("Set BROWSERLESS_TOKEN in Vercel environment variables")

# Correct WebSocket URL
BROWSERLESS_WS = f"wss://chrome.browserless.io/playwright?token={BROWSERLESS_TOKEN}"

# ================= DATA =================
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

    def log(self, msg):
        if self.debug:
            print("[DEBUG]", msg)

    async def wait_for_turnstile(self, page, timeout=10):
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
            async with async_playwright() as p:
                # Connect to Browserless using correct URL with token
                browser = await p.chromium.connect(BROWSERLESS_WS)

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

                self.log("Waiting for Turnstile token")
                token = await self.wait_for_turnstile(page)

                elapsed = round(time.time() - start, 3)
                await browser.close()

                if not token:
                    return TurnstileResult(None, elapsed, "failure", "Turnstile not detected")

                return TurnstileResult(token, elapsed, "success")

        except Exception as e:
            return TurnstileResult(None, round(time.time() - start, 3), "error", str(e))

# ================= API =================
@app.get("/solve")
async def solve_turnstile(request: Request):
    url = request.query_params.get("url")
    if not url:
        return JSONResponse({"error": "Missing url parameter"}, status_code=400)

    url = unquote(url)

    solver = TurnstileSolver(debug=True)
    result = await solver.solve(url)

    return JSONResponse(result.__dict__)
