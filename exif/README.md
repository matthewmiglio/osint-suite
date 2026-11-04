# exif

Image file → embedded EXIF metadata: **GPS location**, camera make/model,
software, and capture timestamps.

```bash
poetry add pillow                                   # one-time: needs Pillow
poetry run python exif/exif_read.py photo.jpg
poetry run python exif/exif_read.py *.jpg --gps-only
poetry run python exif/exif_read.py --selftest      # offline, no Pillow needed
```

- **Consumes:** image paths (JPEG/TIFF/HEIC). Pairs with the Facebook scraper's
  downloaded photos and any saved profile pic.
- **Emits:** `gps` (lat/lon + a Google Maps link) — a new location fact — plus
  camera/device and timestamps for context.
- **Cost:** free.

## Most social images are stripped
Instagram/Facebook/etc. remove EXIF on upload, so "no EXIF" is the common,
expected result — not an error. EXIF survives on files shared as attachments,
pulled from personal sites, or sent uncompressed. When GPS *is* present it's
high-value: fold the lat/lon into the case file and corroborate against other
location facts.
