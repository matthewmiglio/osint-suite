#!/usr/bin/env python
"""phone-intel — phone number -> validity, region, carrier, line type, timezones.

Fully offline: the `phonenumbers` library ships Google's libphonenumber metadata,
so no API and no network. Give an E.164 number (+14155552671) or a national
number plus --region (e.g. --number 4155552671 --region US).
"""
import argparse
import sys

import phonenumbers
from phonenumbers import carrier, geocoder, timezone

TYPES = {
    phonenumbers.PhoneNumberType.MOBILE: "mobile",
    phonenumbers.PhoneNumberType.FIXED_LINE: "fixed line",
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed line or mobile",
    phonenumbers.PhoneNumberType.VOIP: "VoIP",
    phonenumbers.PhoneNumberType.TOLL_FREE: "toll free",
    phonenumbers.PhoneNumberType.PREMIUM_RATE: "premium rate",
    phonenumbers.PhoneNumberType.PAGER: "pager",
    phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "personal number",
}


def intel(number, region=None):
    num = phonenumbers.parse(number, region)
    return {
        "e164": phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164),
        "valid": phonenumbers.is_valid_number(num),
        "country_code": num.country_code,
        "region": geocoder.description_for_number(num, "en") or None,
        "carrier": carrier.name_for_number(num, "en") or None,
        "line_type": TYPES.get(phonenumbers.number_type(num), "unknown"),
        "timezones": list(timezone.time_zones_for_number(num)),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phone number intelligence (offline).")
    ap.add_argument("--number", help="Phone number, e.g. +14155552671")
    ap.add_argument("--region", help="ISO region for national-format numbers, e.g. US")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.number:
        ap.error("--number is required (or --selftest)")
    try:
        info = intel(args.number, args.region)
    except phonenumbers.NumberParseException as e:
        print(f"parse error: {e}", file=sys.stderr)
        return 1
    for k, v in info.items():
        print(f"{k:13}: {v}")
    return 0


def selftest():
    info = intel("+16502530000")   # Google, Mountain View CA
    assert info["valid"] is True, info
    assert info["e164"] == "+16502530000", info
    assert info["country_code"] == 1, info
    assert info["region"], "geocoder returned nothing"
    info2 = intel("6502530000", "US")   # national format needs a region hint
    assert info2["e164"] == "+16502530000", info2
    print("phone-intel selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
