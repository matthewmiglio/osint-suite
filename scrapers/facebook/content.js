// Content script: walks the FB photo lightbox, scraping image + caption + comments per photo.

if (window.__FB_POST_SCRAPER_LOADED__) {
  // already injected
} else {
  window.__FB_POST_SCRAPER_LOADED__ = true;

const log = (...a) => console.log('[fb-scrape]', ...a);
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

let STOP = false;

function progress(text) {
  try { chrome.runtime.sendMessage({ type: 'PROGRESS', text }); } catch (_) {}
}

// ---------- selectors ----------

function getLightboxImage() {
  // Primary: the explicit media-vc-image attribute
  let img = document.querySelector('img[data-visualcompletion="media-vc-image"]');
  if (img && img.src) return img;
  // Fallback: largest fbcdn image currently visible inside a [role="dialog"] or main
  const candidates = [...document.querySelectorAll('div[role="dialog"] img, div[role="main"] img')]
    .filter(i => i.src && i.src.includes('fbcdn') && i.naturalWidth > 200);
  candidates.sort((a, b) => (b.naturalWidth * b.naturalHeight) - (a.naturalWidth * a.naturalHeight));
  return candidates[0] || null;
}

function getNextButton() {
  return document.querySelector('div[aria-label="Next photo"][role="button"]')
      || document.querySelector('[aria-label="Next photo"]');
}

function getPrevButton() {
  return document.querySelector('div[aria-label="Previous photo"][role="button"]')
      || document.querySelector('[aria-label="Previous photo"]');
}

// ---------- text helpers ----------

function visibleText(el) {
  if (!el) return '';
  return (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
}

function getPosterInfo() {
  // The poster header is an <h2 class="html-h2">, with an <a> inside linking to
  // their profile. We must IGNORE generic tab headers like "Photos" / "Posts"
  // that appear in the left-side panel — the real poster <h2> has an <a> whose
  // href is a profile/page link (and usually has aria-label = the name).
  const candidates = document.querySelectorAll('h2.html-h2 a[role="link"], h2 a[role="link"]');
  for (const a of candidates) {
    const href = a.href || '';
    if (!href || /\/photos|\/posts|\/videos|\/about|\/friends/i.test(href)) continue;
    const aria = a.getAttribute('aria-label') || '';
    const txt = visibleText(a);
    const name = (aria || txt || '').trim();
    if (!name) continue;
    if (/^(Photos|Posts|Videos|Reels|About|Friends|Mentions)$/i.test(name)) continue;
    return { name, profileUrl: href.split('?')[0] };
  }
  // Fallback: derive from URL slug
  try {
    const m = location.pathname.match(/^\/([^\/]+)/);
    if (m) {
      const slug = m[1];
      if (!/^(photo|photo\.php|story\.php)/i.test(slug)) {
        return { name: slug.replace(/[._-]/g, ' '), profileUrl: `https://www.facebook.com/${slug}` };
      }
    }
  } catch (_) {}
  return { name: '', profileUrl: '' };
}

// Try to expand comment threads (click "View more comments" / "View N more replies")
async function expandComments(maxRounds = 4) {
  // Find the comments panel (right-side scrollable container). The FB lightbox
  // puts comments inside a separate scroll container; we need to scroll it to
  // trigger lazy-load of comment bodies.
  function findCommentsContainer() {
    // Heuristic: the deepest scrollable ancestor of any [role="article"][aria-label^="Comment by"]
    // OR a div whose direct children include such an article.
    const art = document.querySelector('[role="article"][aria-label^="Comment by"]');
    if (!art) return null;
    let el = art.parentElement;
    while (el && el !== document.body) {
      const cs = getComputedStyle(el);
      if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 10) {
        return el;
      }
      el = el.parentElement;
    }
    return null;
  }

  for (let i = 0; i < maxRounds; i++) {
    // 1) Scroll comments container (loads more + materializes bodies)
    const container = findCommentsContainer();
    if (container) {
      container.scrollTop = container.scrollHeight;
      await sleep(700);
    }
    // 2) Click "View more comments" / "View N replies" / "See more"
    const buttons = [...document.querySelectorAll('div[role="button"], span[role="button"], div[tabindex="0"]')]
      .filter(b => {
        const t = (b.innerText || '').toLowerCase().trim();
        if (!t || t.length > 80) return false;
        return /view\s+(\d+\s+)?(more\s+)?comments?|view\s+(\d+\s+)?(more\s+)?repl(y|ies)|see more comments|previous comments|see more$/i.test(t);
      });
    if (!buttons.length && i > 0) break;
    for (const b of buttons.slice(0, 8)) {
      try { b.click(); } catch (_) {}
      await sleep(350);
    }
    await sleep(900);
  }

  // Final wait to let lazy-loaded bodies render
  await sleep(800);
}

function getDateText() {
  // FB scrambles the visible date via CSS-positioned spans, but the *visible* (innerText) order
  // mostly matches what the user sees. Find the post header date link near the h2.
  const h2 = document.querySelector('h2.html-h2');
  if (!h2) return '';
  const headerRow = h2.closest('div');
  if (!headerRow) return '';
  // The date link usually has target="_blank" and an href with a query string starting with ?bfe or contains the post id
  let dateLink = headerRow.querySelector('a[target="_blank"][href*="?"]')
              || headerRow.parentElement?.querySelector('a[target="_blank"][href*="?"]');
  if (!dateLink) {
    // search nearby anchors
    const anchors = (headerRow.parentElement || headerRow).querySelectorAll('a[role="link"]');
    for (const a of anchors) {
      const t = visibleText(a);
      if (/\d{4}|\d{1,2}:\d{2}|hr|h$|d$|w$|min|month|year|yesterday|today|\bat\b/i.test(t)) {
        dateLink = a;
        break;
      }
    }
  }
  if (!dateLink) return '';
  return visibleText(dateLink);
}

function getCheckIn() {
  // Tagged location at the bottom of the post header row, e.g. "— at Some Place"
  const blocks = document.querySelectorAll('span');
  for (const s of blocks) {
    const t = visibleText(s);
    if (/^—?\s*at\s+/i.test(t) && t.length < 200) {
      const a = s.querySelector('a[href*="facebook.com"]');
      return { text: t.replace(/^—\s*at\s+/i, '').replace(/\.$/, '').trim(), url: a ? a.href.split('?')[0] : '' };
    }
  }
  return { text: '', url: '' };
}

function getCityLocation() {
  // FB sometimes shows "City, Country" as a link next to the date in the header row
  const h2 = document.querySelector('h2.html-h2');
  if (!h2) return { text: '', url: '' };
  const headerRow = h2.closest('div')?.parentElement;
  if (!headerRow) return { text: '', url: '' };
  const anchors = headerRow.querySelectorAll('a[href*="/pages/"]');
  for (const a of anchors) {
    const t = visibleText(a);
    if (t && t.length < 80) return { text: t, url: a.href.split('?')[0] };
  }
  return { text: '', url: '' };
}

// Returns true if the text looks like FB's CSS-positioned scrambled date (lots
// of single-char "words" with spaces between them).
function looksScrambled(s) {
  if (!s || s.length < 8) return false;
  // Count single-character "words" separated by spaces.
  const tokens = s.split(/\s+/).filter(Boolean);
  if (tokens.length < 6) return false;
  const singles = tokens.filter(t => t.length === 1 && /[A-Za-z0-9]/.test(t)).length;
  return singles / tokens.length > 0.5;
}

// Build a comment-body / caption text from a node, preserving emoji <img alt>.
function textWithEmoji(el) {
  if (!el) return '';
  let out = '';
  const walk = (n) => {
    if (n.nodeType === Node.TEXT_NODE) { out += n.nodeValue; return; }
    if (n.nodeType !== Node.ELEMENT_NODE) return;
    if (n.tagName === 'IMG') {
      const alt = n.getAttribute('alt');
      if (alt) out += alt;
      return;
    }
    if (n.tagName === 'BR') { out += '\n'; return; }
    for (const c of n.childNodes) walk(c);
  };
  walk(el);
  return out.replace(/[ \t]+/g, ' ').replace(/\s*\n\s*/g, '\n').trim();
}

function getCaption() {
  // FB post bodies live inside <div class="x1g2khh7"> containers. There can be
  // several of these per post (caption row, "at <location>" row, etc.). The
  // ACTUAL caption is the dir="auto" span inside one of these rows.
  //
  // We skip:
  //  - rows whose visible text starts with "— at " (location tag rows)
  //  - rows whose text is scrambled date noise
  //  - rows whose text equals the poster name
  //  - blocks inside [role="article"][aria-label^="Comment by"] (those are comments)
  const posterName = getPosterInfo().name;
  const rows = document.querySelectorAll('div.x1g2khh7');
  let best = '';
  for (const row of rows) {
    if (row.closest('[role="article"][aria-label^="Comment by"]')) continue;
    // The caption span may or may not have dir="auto". Just take any inline
    // text container (span/div) inside this row.
    const candidates = row.querySelectorAll('span, div');
    for (const sp of candidates) {
      // Skip if this element wraps OTHER candidates with longer text — we want leaf-ish nodes.
      const t = textWithEmoji(sp);
      if (!t || t.length < 2) continue;
      if (posterName && t === posterName) continue;
      if (/^—?\s*at\s+/i.test(t)) continue;
      if (looksScrambled(t)) continue;
      if (/^Like$|^Comment$|^Share$|^Reply$|^See more$|^See less$|^See translation$|^Most relevant$|^Newest$|^All comments$/i.test(t)) continue;
      // Reject if it's just the city-link text or "Public" SVG title
      if (t === 'Shared with Public' || t === 'Public') continue;
      if (t.length > best.length) best = t;
    }
    // Also include direct text-node children of the row
    for (const node of row.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) {
        const t = (node.nodeValue || '').trim();
        if (t.length > best.length) best = t;
      }
    }
  }
  return best.replace(/\s*(See more|See less)$/i, '').trim();
}

function getImageAlt() {
  const img = getLightboxImage();
  return img ? (img.getAttribute('alt') || '') : '';
}

function getImageUrl() {
  const img = getLightboxImage();
  return img ? img.src : '';
}

function getPhotoId() {
  // Lightbox URL typically: /photo/?fbid=XXXX&set=...
  try {
    const u = new URL(location.href);
    return u.searchParams.get('fbid') || '';
  } catch (_) { return ''; }
}

function getComments() {
  const out = [];
  const seen = new Set();
  document.querySelectorAll('div[role="article"][aria-label^="Comment by"]').forEach(node => {
    const aria = node.getAttribute('aria-label') || '';
    // aria-label format: "Comment by <NAME> <relative-time>"
    let name = '';
    let when = '';
    // aria-label format: "Comment by <NAME> <TIME-AGO>"
    // Anchor on the time-ago part at the end so multi-word names don't get split.
    const timeRe = /\s+((?:\d+\s*(?:second|minute|hour|day|week|month|year)s?\s+ago|a\s+(?:few\s+)?(?:second|minute|hour|day|week|month|year)s?\s+ago|yesterday|today|just now))$/i;
    const stripped = aria.replace(/^Comment by\s+/, '');
    const tm = stripped.match(timeRe);
    if (tm) {
      name = stripped.slice(0, tm.index).trim();
      when = tm[1].trim();
    } else {
      name = stripped.trim();
    }

    // Body: prefer the inner "text-align: start" div (the actual comment text),
    // then span[dir=auto][lang], then any longest dir=auto block. Convert emoji.
    let body = '';
    const bodyCandidates = [
      ...node.querySelectorAll('div[dir="auto"][style*="text-align"]'),
      ...node.querySelectorAll('span[dir="auto"][lang]'),
      ...node.querySelectorAll('div[dir="auto"]'),
      ...node.querySelectorAll('span[dir="auto"]'),
    ];
    for (const bn of bodyCandidates) {
      const t = textWithEmoji(bn);
      if (!t) continue;
      if (t === name) continue;
      if (/^Like$|^Reply$|^See translation$|^\d+[wdhms]$|^Author$|^Top fan$|^Most relevant$|^Newest$|^All comments$/i.test(t)) continue;
      if (looksScrambled(t)) continue;
      if (t.length > body.length) body = t;
    }

    // Profile URL: the comment-author's profile link (has comment_id= query param)
    const profileLink = node.querySelector('a[href*="comment_id="]')
                     || node.querySelector('a[href*="facebook.com"][role="link"]')
                     || node.querySelector('a[href*="/profile.php"]');
    const profileUrl = profileLink ? profileLink.href.split('?')[0] : '';

    // Reaction count, if present (e.g. "1 reaction; see who reacted to this")
    let reactions = 0;
    const reactNode = node.querySelector('[aria-label*="reaction"]');
    if (reactNode) {
      const m2 = (reactNode.getAttribute('aria-label') || '').match(/^(\d+)\s+reaction/i);
      if (m2) reactions = parseInt(m2[1], 10);
    }

    const key = `${name}|${body}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ name, when, body, profileUrl, reactions });
  });
  return out;
}

async function scrapeOnePhoto() {
  // Try to expand the comments thread before reading them.
  try { await expandComments(2); } catch (_) {}
  const poster = getPosterInfo();
  const checkIn = getCheckIn();
  const city = getCityLocation();
  return {
    photoId: getPhotoId(),
    pageUrl: location.href,
    poster,
    dateText: getDateText(),
    cityLocation: city,
    checkIn,
    caption: getCaption(),
    imageUrl: getImageUrl(),
    imageAlt: getImageAlt(),
    comments: getComments()
  };
}

// ---------- walking ----------

async function waitForImageChange(prevUrl, maxMs = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs) {
    await sleep(200);
    const img = getLightboxImage();
    if (img && img.src && img.src !== prevUrl && img.complete && img.naturalWidth > 50) return true;
  }
  return false;
}

async function clickNext() {
  const btn = getNextButton();
  if (!btn) return false;
  btn.click();
  return true;
}

async function walk(folder, maxPhotos, delayMs) {
  STOP = false;
  let count = 0;
  const seen = new Set();
  while (!STOP) {
    // Skip if we've seen this photo URL already (catches end-of-album loops)
    let img = getLightboxImage();
    if (!img) { progress('no image found — open a photo first'); break; }
    const url = img.src;
    if (seen.has(url)) { progress(`already saw ${count} unique photos — stopping`); break; }
    seen.add(url);

    progress(`photo ${count + 1}: scraping`);
    const data = await scrapeOnePhoto();
    const res = await chrome.runtime.sendMessage({
      type: 'SAVE_PHOTO',
      payload: { folder, index: count + 1, data }
    });
    if (!res || !res.ok) {
      progress(`save failed at #${count + 1}: ${res && res.error || 'unknown'}`);
      break;
    }
    count++;
    if (maxPhotos > 0 && count >= maxPhotos) { progress(`hit max ${maxPhotos}`); break; }

    // Click next + wait for the lightbox image to swap
    const nextOk = await clickNext();
    if (!nextOk) { progress('no Next button — end of album'); break; }
    await sleep(delayMs);
    const swapped = await waitForImageChange(url, 8000);
    if (!swapped) { progress('next photo did not load — stopping'); break; }
  }
  return count;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg) return;
  if (msg.type === 'STOP') {
    STOP = true;
    sendResponse({ ok: true });
    return;
  }
  if (msg.type === 'WALK') {
    walk(msg.folder || 'fb-scrape', msg.maxPhotos || 0, msg.delayMs || 1500)
      .then(count => sendResponse({ ok: true, count }))
      .catch(err => sendResponse({ ok: false, error: String(err && err.message || err) }));
    return true;
  }
  if (msg.type === 'SCRAPE_ONE') {
    (async () => {
      try {
        const data = await scrapeOnePhoto();
        const r = await chrome.runtime.sendMessage({
          type: 'SAVE_PHOTO',
          payload: { folder: msg.folder || 'fb-scrape', index: 1, data }
        });
        sendResponse(r);
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
});

}
