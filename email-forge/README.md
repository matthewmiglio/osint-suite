# email-forge  (Python, stdlib)

Name + domain → candidate email addresses. Generates the common
personal/corporate address schemes (`john.doe@`, `jdoe@`, `j.doe@`, …) so you can
feed them to `gravatar`, `dehashed`, or an SMTP verifier.

These are **guesses**, not confirmed addresses. Verify before trusting.

```bash
poetry run python email-forge/forge.py --name "John Doe" --domain example.com
poetry run python email-forge/forge.py --selftest      # offline self-check
```

- **Consumes:** name, domain
- **Emits:** candidate emails
- **Cost:** free, offline
