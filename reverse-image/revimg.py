#!/usr/bin/env python
"""reverse-image: upload a local image to a reverse-image engine and scrape who/what it matches.

Yandex only for now (best free face/people engine). Runs HEADED by default so you
can solve the SmartCaptcha yourself; the script waits for results to appear.

    poetry run python reverse-image/revimg.py <image> [--headless] [--timeout 240] [--out shot.png]

Emits: the engine's text guess + external result links (title + domain + url), and
saves a results screenshot. Those domains/names are LEADS, not confirmed ties --
corroborate per the investigate skill's two-tie rule before believing a match.

ponytail: single engine, brittle CSS selectors (Yandex markup drifts), no retries.
Upgrade path when it rots: add --engine google|bing, or swap to their APIs.
"""
import argparse, sys, time, json, re

# Windows consoles default to cp1252 and choke on non-ASCII result names.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

YANDEX = "https://yandex.com/images/"


def run(image, headless, timeout, out):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"),
        )
        page = ctx.new_page()
        page.goto(YANDEX, wait_until="domcontentloaded", timeout=60000)

        # dismiss cookie banner if present (best effort)
        for txt in ("Allow all", "Allow essential cookies", "Accept"):
            try:
                page.get_by_text(txt, exact=False).first.click(timeout=1500)
                break
            except Exception:
                pass

        # the file input exists in the DOM even before the panel opens
        try:
            page.set_input_files("input[type=file]", image, timeout=15000)
        except Exception as e:
            print("UPLOAD_FAILED:", repr(e))
            browser.close()
            return 2

        # wait for results OR captcha; poll so the user can solve a captcha live
        deadline = time.time() + timeout
        state = "waiting"
        warned = False
        while time.time() < deadline:
            url = page.url
            body = (page.inner_text("body")[:400] if page.query_selector("body") else "").lower()
            captcha = ("captcha" in url or "showcaptcha" in url
                       or "i'm not a robot" in body or "confirm that you" in body
                       or "подтвердите" in body)
            has_results = ("rpt=imageview" in url or "cbir" in url.lower()) and \
                          page.query_selector("a[href^='http']:not([href*='yandex'])") is not None
            if captcha and not has_results:
                if not warned:
                    print(">>> CAPTCHA shown -- solve it in the browser window; waiting...",
                          flush=True)
                    warned = True
                time.sleep(3)
                continue
            if has_results:
                state = "results"
                break
            time.sleep(2)

        page.wait_for_timeout(1500)
        try:
            page.screenshot(path=out, full_page=False)
        except Exception:
            pass

        # engine's own guess (the query Yandex fills in after a visual search)
        guess = ""
        for sel in ("input.mini-suggest__input", "input[name='text']",
                    ".CbirObjectResponse-Title", ".CbirNavigation-TabsItem_name_similar-page"):
            el = page.query_selector(sel)
            if el:
                guess = (el.get_attribute("value") or el.inner_text() or "").strip()
                if guess:
                    break

        # external result links = the actual leads
        links = page.eval_on_selector_all(
            "a[href^='http']",
            """els => els.map(a => ({t:(a.innerText||'').trim().slice(0,90), h:a.href}))
                        .filter(x => x.h && !/yandex\\./.test(x.h))"""
        )
        seen, out_links = set(), []
        for L in links:
            dom = re.sub(r"^https?://([^/]+)/?.*$", r"\1", L["h"])
            key = (dom, L["t"][:40])
            if key in seen or not L["t"]:
                continue
            seen.add(key)
            out_links.append({"domain": dom, "text": L["t"], "url": L["h"]})

        result = {
            "state": state,
            "engine_guess": guess,
            "result_count": len(out_links),
            "results": out_links[:25],
            "screenshot": out,
        }
        blob = json.dumps(result, ensure_ascii=False, indent=2)
        with open(out + ".json", "w", encoding="utf-8") as f:  # survives console encoding
            f.write(blob)
        print(blob)
        browser.close()
        return 0 if state == "results" else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--headless", action="store_true", help="no window (captchas will block)")
    ap.add_argument("--timeout", type=int, default=240, help="seconds to wait for results/captcha")
    ap.add_argument("--out", default="reverse-image/_result.png", help="results screenshot path")
    a = ap.parse_args()
    return run(a.image, a.headless, a.timeout, a.out)


if __name__ == "__main__":
    sys.exit(main())
