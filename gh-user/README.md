# gh-user

GitHub username → public profile **plus commit-author emails** scraped from the
user's recent public push events.

```bash
poetry run python gh-user/gh.py octocat
GITHUB_TOKEN=ghp_xxx poetry run python gh-user/gh.py octocat   # 60→5000 req/hr
poetry run python gh-user/gh.py --selftest                     # offline, no network
```

- **Consumes:** a GitHub username.
- **Emits:** name, company, blog, location, bio, public profile email, and
  **commit-author emails** from PushEvents. A commit email is a **strong new
  selector** — feed it to `gravatar` / `dehashed`.
- **Cost:** free, keyless. Unauth limit 60 req/hr; set `GITHUB_TOKEN` (read from
  the environment automatically) for 5000/hr.

## Why commit emails matter
Developers routinely hide their profile email but leak a real one in `git`
commit metadata. This module surfaces those from the last ~100 public events
(`noreply.github.com` addresses are dropped). Still verify before pivoting — a
commit email can belong to a co-author or an old address.

## Notes (live-tested 2026-11)

- GitHub's events API no longer includes `commits[]` in PushEvent payloads (only
  `head`/`before` SHAs). If no emails come from the payload, the tool looks up the
  head commit of the most recent push in up to 5 distinct repos
  (`/repos/<repo>/commits/<sha>`, 1 request each) and keeps only author/committer
  identities whose GitHub login is the target (a head can be someone else's patch).
- Many users commit with `noreply.github.com` addresses, which are dropped, so
  "no commit emails" is a common, valid result.
- The events endpoint only covers ~90 days / 300 events; dormant users show nothing.
- Rate limit (HTTP 403/429) prints a one-line error with reset time and exits 2.
  `GITHUB_TOKEN` is sent as `Authorization: Bearer` when set.
