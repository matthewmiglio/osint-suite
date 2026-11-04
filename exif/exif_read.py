#!/usr/bin/env python
"""exif — image file -> EXIF metadata (GPS, camera, timestamps).

Mines the metadata that cameras/phones embed in JPEG/TIFF/HEIC: where and when a
photo was taken, and on what device. The high-value selector is GPS — a lat/lon
is a new location fact you can fold into the case file. Feeds naturally from the
facebook scraper's downloaded photos and from any profile pic you've saved.

Needs Pillow (`poetry add pillow`). GPS/camera parsing is split from the file
read so the decoding logic stays testable offline (see --selftest). Most photos
posted to social media are STRIPPED of EXIF by the platform on upload — a result
of "no EXIF" is the common case, not an error.

USAGE
    poetry run python exif/exif_read.py photo.jpg
    poetry run python exif/exif_read.py ig-scrape/*.jpg --gps-only
    poetry run python exif/exif_read.py --selftest          # offline, no Pillow needed
"""
import argparse
import sys

# EXIF numeric tag ids we care to name (subset of PIL.ExifTags.TAGS).
WANT = {
    271: "Make", 272: "Model", 305: "Software",
    306: "DateTime", 36867: "DateTimeOriginal", 36868: "DateTimeDigitized",
    42035: "LensMake", 42036: "LensModel", 315: "Artist", 33432: "Copyright",
}
GPS_IFD = 34853


def _ratio(v):
    """IFDRational / (num,den) tuple / number -> float."""
    try:
        f = float(v)                         # IFDRational and plain numbers
        return 0.0 if f != f else f          # IFDRational(0,0) -> nan
    except TypeError:
        return v[0] / v[1] if v[1] else 0.0  # legacy (num, den) tuple


def to_decimal(dms, ref):
    """((d),(m),(s)) + 'N'/'S'/'E'/'W' -> signed decimal degrees."""
    d, m, s = (_ratio(x) for x in dms)
    dec = d + m / 60.0 + s / 3600.0
    return -dec if ref in ("S", "W") else dec


def parse_gps(gps):
    """GPS IFD (numeric-keyed: 1=latref 2=lat 3=lonref 4=lon) -> {lat, lon} or None."""
    if not gps or 2 not in gps or 4 not in gps:
        return None
    return {
        "lat": round(to_decimal(gps[2], gps.get(1, "N")), 6),
        "lon": round(to_decimal(gps[4], gps.get(3, "E")), 6),
    }


def parse(exif):
    """Numeric-keyed EXIF dict (flattened by read_file()) -> {fields..., gps, maps}."""
    if not exif:
        return {}
    out = {name: exif[tag] for tag, name in WANT.items() if tag in exif}
    gps = parse_gps(exif.get(GPS_IFD))
    if gps:
        out["gps"] = gps
        out["maps"] = f"https://www.google.com/maps?q={gps['lat']},{gps['lon']}"
    return out


def read_file(path):
    from PIL import Image  # lazy: --selftest needs no Pillow
    with Image.open(path) as img:
        ex = img.getexif()  # public API (works for JPEG/TIFF/PNG/WebP/HEIC)
        if not ex:
            return {}
        data = dict(ex)
        data.update(ex.get_ifd(0x8769))      # Exif sub-IFD: DateTimeOriginal, Lens*
        gps = ex.get_ifd(GPS_IFD)            # GPS sub-IFD
        if gps:
            data[GPS_IFD] = dict(gps)
        return data


def report(path, data, gps_only):
    if not data:
        return f"{path}\n  (no EXIF: stripped on upload, or none embedded)"
    if gps_only:
        g = data.get("gps")
        return f"{path}\n  {data['maps']}" if g else f"{path}\n  (no GPS)"
    lines = [path]
    for k, v in data.items():
        if k != "maps":
            lines.append(f"  {k}: {v}")
    if "maps" in data:
        lines.append(f"  maps: {data['maps']}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Extract EXIF (GPS/camera/time) from image files.")
    ap.add_argument("images", nargs="*", help="one or more image paths")
    ap.add_argument("--gps-only", action="store_true", help="only report location")
    ap.add_argument("--selftest", action="store_true", help="offline decoder check")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.images:
        ap.error("give one or more image paths, or --selftest")
    for path in args.images:
        try:
            print(report(path, parse(read_file(path)), args.gps_only))
        except Exception as e:
            print(f"{path}\n  error: {e}")
    return 0


def selftest():
    # the real logic is GPS DMS->decimal and the IFD mapping; test offline.
    assert abs(to_decimal(((40, 1), (42, 1), (3, 1)), "N") - 40.700833) < 1e-5
    assert to_decimal(((40, 1), (0, 1), (0, 1)), "S") == -40.0, "southern hemisphere negative"
    g = parse_gps({1: "N", 2: ((51, 1), (30, 1), (0, 1)), 3: "W", 4: ((0, 1), (7, 1), (0, 1))})
    assert g == {"lat": 51.5, "lon": -0.116667}, g
    assert parse_gps({1: "N"}) is None, "missing coords -> None"
    d = parse({272: "Pixel 7", 36867: "2024:01:02 03:04:05", GPS_IFD: {2: ((1, 1),) * 3, 4: ((2, 1),) * 3}})
    assert d["Model"] == "Pixel 7" and "gps" in d and "maps" in d, d
    assert parse({}) == {} and parse(None) == {}, "empty exif"
    print("exif selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
