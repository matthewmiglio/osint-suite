# email-accounts

Email → which sites have an account registered to that address. Thin wrapper
around [`holehe`](https://github.com/megadose/holehe), which probes 120+ sites'
password-reset / signup endpoints **without alerting the target**.

```bash
poetry add holehe                                     # one-time: needs holehe
poetry run python email-accounts/accounts.py foo@bar.com
poetry run python email-accounts/accounts.py foo@bar.com --timeout 60
poetry run python email-accounts/accounts.py --selftest   # offline parser check
```

- **Consumes:** an email address. The email-side counterpart to `username-enum`.
- **Emits:** the list of sites where the email is registered — each a lead to a
  profile/account.
- **Cost:** free (holehe does unauthenticated endpoint probes).

## Wrapper, not a reinvention
120 per-site probes break constantly; `holehe` already maintains them, so this
module just runs `holehe <email> --only-used` and parses the `[+]` lines. If
holehe isn't installed it exits with an install hint (code 2). A "used" result is
a **lead** — forwarding addresses and false positives exist; corroborate before
folding an identity link in.
