# reverse-image  (Python, shared env + Playwright)

Upload a local image to a reverse-image engine and scrape who/what it matches.
The high-value OSINT use: a **face/tattoo match** is one of the strongest ties
between two profiles — it corroborates a link that a shared handle alone cannot.

Yandex only for now (best free engine for faces/people).

## Install
Playwright + its Chromium are part of the shared Poetry env:

```bash
poetry install
poetry run playwright install chromium   # one-time browser download
```

## Run
```bash
poetry run python reverse-image/revimg.py <image> [--headless] [--timeout 240] [--out shot.png]
```

Runs **headed by default** so you can solve Yandex's SmartCaptcha in the window;
the script waits for results to appear, then scrapes them. `--headless` skips the
window but a captcha will then just time out.

Outputs JSON: the engine's text guess, external result links (title + domain +
url), and a results screenshot (`--out`, default `reverse-image/_result.png`).

## Reading the output (important)
Result domains/names are **leads, not proof**. A visual match still has to clear
the investigate skill's **two-tie rule** before you treat two profiles as the same
person: a face match is a strong tie, but confirm with a second independent one
(shared email/phone, self-reference, etc.) before folding a cluster into the target.

## Limits
- Single engine, brittle CSS selectors (Yandex markup drifts), no retries.
  Upgrade path: add `--engine google|bing` or move to their APIs.
- Yandex anti-bot may captcha every run; that's why it's headed.
