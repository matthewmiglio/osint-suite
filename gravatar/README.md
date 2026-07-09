# gravatar  (Python, stdlib + requests)

Email → Gravatar avatar URL and public profile. The hash (md5 of the trimmed,
lowercased email) is built offline; `--fetch` pulls the public profile JSON
(displayName, name, location, linked social accounts) over the network.

A profile hit means the target reused an email that has a public Gravatar.

```bash
poetry run python gravatar/gravatar.py --email foo@bar.com
poetry run python gravatar/gravatar.py --email foo@bar.com --fetch   # network
poetry run python gravatar/gravatar.py --selftest                    # offline self-check
```

- **Consumes:** email
- **Emits:** avatar URL, profile URL, and (with `--fetch`) name / location / linked accounts
- **Cost:** free (no key)
