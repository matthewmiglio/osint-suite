# username-enum

Username → which sites have an account with that handle. Sherlock-style: hit each
site's profile URL and decide **exists / absent / unknown** from the status code
or a page marker. Threaded, so a ~17-site sweep is a couple of seconds.

```bash
poetry run python username-enum/username_enum.py korrart
poetry run python username-enum/username_enum.py korrart --only github,keybase,telegram
poetry run python username-enum/username_enum.py --selftest     # offline, no network
```

- **Consumes:** a username/handle.
- **Emits:** profile URLs on sites where the handle exists → each is a new place
  to scrape names/bios/more handles.
- **Cost:** free (direct HTTP, no API key).

## Detection is heuristic — a hit is a LEAD, not a link
Social sites block bots and soft-404 (HTTP 200 + a "not found" page), so:
- `exists` means "the handle's profile URL resolved" — go look at it.
- Handles collide. Same handle on another site is a **lead**, not proof it's the
  same person (see the /investigate two-independent-ties rule). Confirm with a
  second tie (same face/email/bio) before folding a link into the case file.

## Extending the site list
`SITES` in `username_enum.py` is a plain dict: `name: (url_template, method, marker)`.
- `method="status"` → exists if HTTP 200, absent if 404.
- `method="string"` → site 200s for everyone; exists if `marker` is in the body.

Add a row, run it against a handle you know exists and one you know doesn't, and
keep it only if both verdicts are right. The shipped list is curated, not
exhaustive — blocked sites often return `unknown`. Live-tested; removed as unreliable: Instagram, Twitch (JS shell, 200 for everyone), Reddit, GitLab (403 bot-block / API returns [] for real users). Fixed: Wordpress (signup-redirect + 410), DockerHub (API URL), Steam (not-found text).
