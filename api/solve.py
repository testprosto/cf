import os
import time
from typing import Optional
from dataclasses import dataclass
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright

app = FastAPI()

# ================= DATA ==================
@dataclass
class TurnstileResult:
    turnstile_value: Optional[str]
    elapsed_time_seconds: float
    status: str
    reason: Optional[str] = None

# ================= SOLVER =================
class TurnstileSolver:

    def __init__(self, headless=True, useragent=None, debug=False):
        self.headless = headless
        self.useragent = useragent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        self.debug = debug

    def _debug(self, msg):
        if self.debug:
            print(f"[DEBUG] {msg}")

    async def _wait_for_turnstile(self, page, timeout=10):
        """
        Wait for Turnstile token to appear
        """
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

    async def solve(self, url: str, cookies: dict = None) -> TurnstileResult:
        start = time.time()
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled",
                          "--no-sandbox",
                          "--disable-dev-shm-usage"]
                )
                context = await browser.new_context(
                    user_agent=self.useragent,
                    viewport={"width": 1280, "height": 900}
                )
                if cookies:
                    domain = url.split("//")[1].split("/")[0]
                    await context.add_cookies([
                        {"name": k, "value": str(v), "domain": domain, "path": "/"}
                        for k, v in cookies.items()
                    ])
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                self._debug("Page loaded, waiting for Turnstile...")
                token = await self._wait_for_turnstile(page)
                elapsed = round(time.time() - start, 3)
                await browser.close()
                if not token:
                    return TurnstileResult(
                        None,
                        elapsed,
                        "failure",
                        "Turnstile token not detected"
                    )
                return TurnstileResult(token, elapsed, "success")
        except Exception as e:
            return TurnstileResult(
                None,
                round(time.time() - start, 3),
                "error",
                str(e)
            )

# ================= API ENDPOINT =================
@app.get("/solve")
async def solve_turnstile(request: Request):
    """
    Example usage:
    https://your-vercel-url/solve?url=https%3A%2F%2Fexample.com&sitekey=123
    """
    url = request.query_params.get("url")
    sitekey = request.query_params.get("sitekey")  # legacy, unused but kept

    if not url:
        return JSONResponse({"error": "Missing 'url' parameter"}, status_code=400)

    # decode url if encoded
    url = unquote(url)

    solver = TurnstileSolver(headless=True, debug=True)
    result = await solver.solve(url)

    return JSONResponse(result.__dict__)
