# FB Post Scraper (Chrome extension)

Walks a Facebook photo album / profile photos lightbox, scraping each photo's image, caption, location, poster, date, and visible comments into per-photo folders under your Downloads directory.

## Install (unpacked)
1. Chrome → `chrome://extensions`
2. Enable **Developer mode** (top right).
3. **Load unpacked** → select `C:\My_Files\my_programs\fb-post-scraper\`.
4. Pin the extension (puzzle icon → pin).

## Use
1. Log into Facebook.
2. Navigate to the target person's **Photos** tab (e.g. `https://www.facebook.com/<username>/photos`).
3. Click any photo to open it in the lightbox.
4. Click the extension icon.
5. Set:
   - **Folder name** — output folder under Downloads (default `fb-scrape`).
   - **Max photos** — `0` for unlimited, otherwise a cap (good for testing).
   - **Delay between photos (ms)** — `1500` is safe; increase if scrape misses data.
6. Click **Start scraping**.

The extension clicks the lightbox's "Next photo" button between each scrape and stops when:
- it sees a photo URL it's already scraped (loop detected),
- the Next button disappears,
- you hit **Stop**, or
- it hits the max-photos cap.

### Single-photo mode
Click **Scrape current photo only** to grab just the lightbox photo without walking.

## Output
For each photo:
```
Downloads/<folder>/photo-001/
  photo.jpg
  data.json
Downloads/<folder>/photo-002/
  photo.jpg
  data.json
...
```

`data.json` schema:
```json
{
  "photoId": "10163...",
  "pageUrl": "https://www.facebook.com/photo/?fbid=...",
  "poster": { "name": "...", "profileUrl": "..." },
  "dateText": "Jan 1, 2024",
  "cityLocation": { "text": "City, Country", "url": "..." },
  "checkIn": { "text": "Place name", "url": "..." },
  "caption": "Full visible caption text",
  "imageUrl": "https://scontent-...fbcdn.net/...jpg",
  "imageAlt": "...",
  "comments": [
    { "name": "Commenter Name", "when": "a year ago", "body": "Comment text", "profileUrl": "..." }
  ],
  "imagePath": "fb-scrape/photo-001/photo.jpg",
  "scrapedAt": "2026-05-19T..."
}
```

## Tips
- **Date text is sometimes garbled** because FB scrambles it with CSS-positioned spans for anti-scraping. The script uses `innerText` which is usually still correct — but if it looks off, the `pageUrl` of the post is your source of truth.
- **Comments only include what's expanded.** Click "View previous comments" + "Reply" expansion before scraping if you want full coverage.
- **Tagged people in photos** are not currently extracted (FB shows them on hover only). To get them, hover over the photo first.
- The script de-duplicates by image URL, so the same photo seen twice (e.g. profile pic showing up at start of every album) will only be scraped once.
- If you see "next photo did not load — stopping", FB throttled — increase the delay and re-run.

## After scraping
Move the resulting folder somewhere under your Downloads directory for analysis (you can rename it on the Downloads side or just `move`).
