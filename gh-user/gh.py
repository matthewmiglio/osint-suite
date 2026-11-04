#!/usr/bin/env python
"""gh-user — GitHub username -> profile + commit-author emails.

Two free, keyless GitHub API calls:
  /users/<u>              -> name, company, blog, location, bio, public email
  /users/<u>/events/public -> commit-author emails from recent PushEvents
A commit email is the prize: GitHub users routinely leak a real email in their
commit metadata even when the profile email is hidden. That email is a STRONG new
selector — fold it straight into gravatar / dehashed.

Unauth rate limit is 60 req/hr. Set GITHUB_TOKEN in the environment to raise it
to 5000/hr (the module reads it if present, no flag needed). The JSON parsing is
split from the fetch so it stays testable offline (see --selftest).

USAGE
    poetry run python gh-user/gh.py octocat
    GITHUB_TOKEN=ghp_xxx poetry run python gh-user/gh.py octocat
    poetry run python gh-user/gh.py --selftest          # offline, no network
"""
import argparse
import os
import sys

API = "https://api.github.com"


def _headers():
    h = {"User-Agent": "osint-suite", "Accept": "application/vnd.github+json"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = "Bearer " + tok
    return h


class GitHubError(Exception):
    """Friendly, non-traceback failure (rate limit, network, bad status)."""


def _get(url, h):
    import requests  # lazy: keep network dep off --selftest
    try:
        r = requests.get(url, headers=h, timeout=15)
    except requests.RequestException as e:
        raise GitHubError(f"network error: {e}")
    if r.status_code in (403, 429) and (
            r.headers.get("x-ratelimit-remaining") == "0" or r.status_code == 429
            or "rate limit" in r.text.lower()):
        reset = r.headers.get("x-ratelimit-reset")
        when = ""
        if reset and reset.isdigit():
            import time
            when = f" Resets in ~{max(0, int(reset) - int(time.time())) // 60} min."
        hint = "" if os.environ.get("GITHUB_TOKEN") else " Set GITHUB_TOKEN to raise the limit to 5000/hr."
        raise GitHubError("GitHub API rate limit hit." + when + hint)
    return r


def fetch(user, max_lookups=5):
    h = _headers()
    pr = _get(f"{API}/users/{user}", h)
    if pr.status_code == 404:
        return None, [], {}
    if not pr.ok:
        raise GitHubError(f"GitHub returned HTTP {pr.status_code} for profile")
    ev = _get(f"{API}/users/{user}/events/public?per_page=100", h)
    if not ev.ok:
        raise GitHubError(f"GitHub returned HTTP {ev.status_code} for events")
    events = ev.json()
    extra = {}
    if not commit_emails(events):
        # GitHub no longer embeds commits[] in PushEvent payloads; look up the
        # head commit of the most recent push per repo (1 request each, capped).
        for repo, sha in push_heads(events)[:max_lookups]:
            r = _get(f"{API}/repos/{repo}/commits/{sha}", h)
            if r.ok:
                for em, nm in head_commit_emails(r.json(), user).items():
                    extra.setdefault(em, nm)
    return pr.json(), events, extra


def push_heads(events):
    """Most recent (repo, head_sha) per repo from PushEvents (newest first)."""
    seen, out = set(), []
    for e in events or []:
        if e.get("type") != "PushEvent":
            continue
        repo = (e.get("repo") or {}).get("name")
        sha = (e.get("payload") or {}).get("head")
        if repo and sha and repo not in seen:
            seen.add(repo)
            out.append((repo, sha))
    return out


def head_commit_emails(c, user):
    """/repos/x/commits/sha JSON -> {email: name}, only identities that are `user`
    (a pushed head can be someone else's patch, e.g. a maintainer merging)."""
    out = {}
    for who, key in (("author", "author"), ("committer", "committer")):
        login = ((c.get(who) or {}).get("login") or "").lower()
        a = (c.get("commit") or {}).get(key) or {}
        email = (a.get("email") or "").strip().lower()
        if login == user.lower() and email and "noreply.github.com" not in email:
            out.setdefault(email, a.get("name"))
    return out


def profile_fields(p):
    """GitHub user JSON -> ordered (label, value) pairs, skipping blanks."""
    want = [("name", "name"), ("company", "company"), ("blog", "blog"),
            ("location", "location"), ("email", "email"), ("bio", "bio"),
            ("twitter_username", "twitter"), ("public_repos", "repos"),
            ("followers", "followers"), ("created_at", "created"),
            ("html_url", "url")]
    return [(label, p[key]) for key, label in want if p.get(key)]


def commit_emails(events):
    """PushEvent payloads -> {email: name} from commit authors (noreply dropped)."""
    out = {}
    for e in events or []:
        if e.get("type") != "PushEvent":
            continue
        for c in e.get("payload", {}).get("commits", []):
            a = c.get("author", {})
            email = (a.get("email") or "").strip().lower()
            if email and "noreply.github.com" not in email:
                out.setdefault(email, a.get("name"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="GitHub profile + leaked commit emails for a username.")
    ap.add_argument("user", nargs="?", help="GitHub username")
    ap.add_argument("--selftest", action="store_true", help="offline parser check")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.user:
        ap.error("give a GitHub username, or --selftest")

    try:
        profile, events, extra = fetch(args.user)
    except GitHubError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if profile is None:
        print(f"no such GitHub user: {args.user}")
        return 1
    for label, val in profile_fields(profile):
        print(f"{label:9} {val}")
    emails = commit_emails(events)
    for em, nm in extra.items():
        emails.setdefault(em, nm)
    if emails:
        print("\ncommit-author emails (NEW selectors: verify before pivoting):")
        for email, name in emails.items():
            print(f"  {email}  ({name})")
    else:
        print("\n(no commit emails in recent public events)")
    return 0


def selftest():
    p = {"name": "The Octocat", "email": "octo@github.com", "company": "@github",
         "blog": "", "html_url": "https://github.com/octocat", "public_repos": 8}
    f = dict(profile_fields(p))
    assert f["name"] == "The Octocat" and f["email"] == "octo@github.com"
    assert "blog" not in f, "blank fields dropped"
    events = [
        {"type": "PushEvent", "payload": {"commits": [
            {"author": {"email": "Real@Dev.com", "name": "Real Dev"}},
            {"author": {"email": "1234+bot@users.noreply.github.com", "name": "x"}},
        ]}},
        {"type": "WatchEvent", "payload": {}},
    ]
    em = commit_emails(events)
    assert em == {"real@dev.com": "Real Dev"}, em  # lowercased, noreply dropped
    assert commit_emails([]) == {}
    # modern PushEvent (no commits[]): head lookup path
    pe = [{"type": "PushEvent", "repo": {"name": "a/b"}, "payload": {"head": "abc"}},
          {"type": "PushEvent", "repo": {"name": "a/b"}, "payload": {"head": "old"}},
          {"type": "PushEvent", "repo": {"name": "c/d"}, "payload": {"head": "def"}}]
    assert push_heads(pe) == [("a/b", "abc"), ("c/d", "def")]
    c = {"author": {"login": "Me"}, "committer": {"login": "other"},
         "commit": {"author": {"email": "Me@X.com", "name": "Me"},
                    "committer": {"email": "o@y.com", "name": "O"}}}
    assert head_commit_emails(c, "me") == {"me@x.com": "Me"}, "foreign committer dropped"
    print("gh-user selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
