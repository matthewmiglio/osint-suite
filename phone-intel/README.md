# phone-intel  (Python, phonenumbers)

Phone number → validity, region, carrier, line type, and timezones. Fully
**offline** — the `phonenumbers` library ships Google's libphonenumber metadata,
so no API and no network.

```bash
poetry run python phone-intel/phone.py --number "+14155552671"
poetry run python phone-intel/phone.py --number 4155552671 --region US
poetry run python phone-intel/phone.py --selftest
```

Give an E.164 number, or a national number plus `--region` (ISO code).

- **Consumes:** phone
- **Emits:** E.164, valid?, country code, region/geo, carrier, line type, timezones
- **Cost:** free, offline
