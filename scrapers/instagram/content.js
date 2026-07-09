// Content script: scrapes a target IG profile's followers + following lists
// (handle, name, profile pic) from the followers/following modals into
// Downloads/ig-scrape-<handle>/. Injected by popup.js with window.__IG_SCRAPE_CONFIG.
(async function () {
  if (window.__IG_SCRAPE_RUNNING) return;
  window.__IG_SCRAPE_RUNNING = true;
  window.__IG_SCRAPE_STOP = false;

  const cfg = window.__IG_SCRAPE_CONFIG || {};
  const targetHandle = (cfg.handle || '').trim().replace(/^@/, '');
  const downloadPics = cfg.downloadPics !== false;

  const delay = (ms) => new Promise((r) => setTimeout(r, ms));
  const shouldStop = () => window.__IG_SCRAPE_STOP === true;

  const log = (msg) => {
    console.log(`[IG] ${msg}`);
    try { chrome.runtime.sendMessage({ type: 'log', text: msg }); } catch (e) {}
  };
  const sendStats = (stats) => {
    try { chrome.runtime.sendMessage({ type: 'stats', stats }); } catch (e) {}
  };
  const send = (type, payload) => new Promise((resolve) => {
    chrome.runtime.sendMessage({ type, ...payload }, (res) => resolve(res));
  });

  // ---- Navigation -------------------------------------------------------
  async function ensureOnProfile() {
    const want = `/${targetHandle}/`;
    if (!location.pathname.startsWith(want)) {
      log(`Navigating to https://www.instagram.com/${targetHandle}/`);
      location.href = `https://www.instagram.com/${targetHandle}/`;
      // The script will be re-injected after navigation; abort this run.
      return false;
    }
    // Wait for page to settle
    for (let i = 0; i < 40; i++) {
      const hasHeader = document.querySelector('header') || document.querySelector('main');
      if (hasHeader) break;
      await delay(300);
    }
    await delay(800);
    return true;
  }

  // Private-profile detector.
  // IG private landing page contains:
  //  - literal text "This profile is private" / "This account is private"
  //  - a padlock SVG (viewBox "0 0 96 96") inside main
  // Either signal alone is sufficient.
  function isPrivateProfile() {
    const main = document.querySelector('main') || document.body;
    const txt = (main.innerText || '').toLowerCase();
    if (txt.includes('this account is private') || txt.includes('this profile is private')) return true;
    if (main.querySelector('svg[viewBox="0 0 96 96"]')) return true;
    return false;
  }

  // ---- Open list modal --------------------------------------------------
  function findListButton(kind) {
    // kind: 'followers' | 'following'
    // Prefer href ending with the kind
    const links = document.querySelectorAll('a[href]');
    for (const a of links) {
      try {
        const u = new URL(a.href, location.origin);
        if (u.pathname === `/${targetHandle}/${kind}/`) return a;
      } catch (e) {}
    }
    // Fallback by text content
    for (const a of links) {
      const t = (a.textContent || '').trim().toLowerCase();
      if (t.endsWith(kind)) return a;
    }
    return null;
  }

  async function openList(kind) {
    log(`Opening ${kind} list...`);
    closeAnyDialog();
    await delay(500);
    const btn = findListButton(kind);
    if (!btn) throw new Error(`Could not find ${kind} button`);
    btn.click();
    // Wait for dialog
    let dialog = null;
    for (let i = 0; i < 60; i++) {
      dialog = document.querySelector('div[role="dialog"]');
      if (dialog && dialog.querySelector('img[alt$="profile picture"]')) break;
      await delay(300);
    }
    if (!dialog) throw new Error(`${kind} modal did not open`);
    await delay(800);
    return dialog;
  }

  function closeAnyDialog() {
    const dialog = document.querySelector('div[role="dialog"]');
    if (!dialog) return;
    // Try aria-label Close
    const closeBtn = dialog.querySelector('svg[aria-label="Close"]');
    if (closeBtn) {
      const clickable = closeBtn.closest('div[role="button"]') || closeBtn.parentElement;
      clickable && clickable.click();
      return;
    }
    // Press Escape as fallback
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true }));
  }

  // ---- Scrape rows from current modal -----------------------------------
  function findScrollContainer(dialog) {
    const all = dialog.querySelectorAll('div');
    let best = null;
    for (const div of all) {
      if (div.scrollHeight > div.clientHeight + 20) {
        const style = getComputedStyle(div);
        if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
          if (!best || div.clientHeight > best.clientHeight) best = div;
        }
      }
    }
    return best;
  }

  function scrapeVisibleRows(dialog, seen) {
    const out = [];
    const imgs = dialog.querySelectorAll('img[alt$="profile picture"]');
    for (const img of imgs) {
      const m = img.alt.match(/^(.+)'s profile picture$/);
      if (!m) continue;
      const handle = m[1].trim();
      if (!handle || seen.has(handle)) continue;

      // Find row container: walk up until we find element that also contains
      // an anchor to /handle/
      let row = img;
      for (let i = 0; i < 12; i++) {
        if (!row || !row.parentElement) break;
        row = row.parentElement;
        const a = row.querySelector(`a[href="/${handle}/"]`);
        const spans = row.querySelectorAll('span');
        if (a && spans.length >= 2) break;
      }

      // Nickname: any span text inside row that isn't the handle and isn't a button label
      let nickname = '';
      const spanNodes = row ? row.querySelectorAll('span') : [];
      for (const sp of spanNodes) {
        // Only leaf-ish spans
        if (sp.querySelector('span')) continue;
        const t = (sp.textContent || '').trim();
        if (!t) continue;
        if (t === handle) continue;
        const lower = t.toLowerCase();
        if (lower === 'follow' || lower === 'following' || lower === 'follow back' || lower === 'requested' || lower === 'message') continue;
        if (lower === 'verified') continue;
        nickname = t;
        break;
      }

      out.push({ handle, nickname, profilePic: img.src });
      seen.add(handle);
    }
    return out;
  }

  async function scrollAndScrape(kind, dialog) {
    const seen = new Set();
    const collected = [];
    const scrollEl = findScrollContainer(dialog);
    if (!scrollEl) {
      log(`[WARN] scroll container not found for ${kind}, trying without scrolling`);
    } else {
      log(`Found scroll container (h=${scrollEl.clientHeight}, sh=${scrollEl.scrollHeight})`);
    }

    let stable = 0;
    let lastCount = -1;
    let iterations = 0;

    while (!shouldStop()) {
      const fresh = scrapeVisibleRows(dialog, seen);
      collected.push(...fresh);

      const statKey = kind === 'followers' ? 'followers' : 'following';
      sendStats({ phase: kind, [statKey]: collected.length });

      if (collected.length === lastCount) {
        stable++;
        if (stable >= 6) {
          log(`${kind}: count stable at ${collected.length}, done`);
          break;
        }
      } else {
        stable = 0;
        lastCount = collected.length;
      }

      if (scrollEl) {
        scrollEl.scrollTop = scrollEl.scrollHeight;
      } else {
        // try scrolling the dialog itself
        dialog.scrollTop = dialog.scrollHeight;
      }
      // small jitter to nudge IG into loading next page
      await delay(900);
      if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
      await delay(600);

      iterations++;
      if (iterations % 10 === 0) {
        log(`${kind}: scraped ${collected.length} so far (iter ${iterations})`);
      }
      if (iterations > 4000) {
        log(`[WARN] ${kind}: hit safety cap of 4000 scroll iterations`);
        break;
      }
    }

    return collected;
  }

  // ---- Save results -----------------------------------------------------
  async function saveList(kind, rows) {
    const payload = {
      sourceHandle: targetHandle,
      kind,
      scrapedAt: new Date().toISOString(),
      count: rows.length,
      entries: rows
    };
    const res = await send('saveData', { handle: targetHandle, filename: `${kind}.json`, data: payload });
    if (res && res.ok) log(`Saved ${kind}.json (${rows.length} entries) -> ${res.path}`);
    else log(`[ERR] Failed to save ${kind}.json: ${res && res.error}`);

    if (downloadPics) {
      log(`Downloading ${rows.length} ${kind} profile pictures...`);
      let i = 0;
      for (const r of rows) {
        if (shouldStop()) break;
        i++;
        await send('saveImage', { handle: targetHandle, subdir: `${kind}-pics`, name: r.handle, url: r.profilePic });
        if (i % 25 === 0) log(`${kind} pics: ${i}/${rows.length}`);
      }
      log(`Finished ${kind} pictures (${i}/${rows.length})`);
    }
  }

  // ---- Main -------------------------------------------------------------
  try {
    if (!targetHandle) throw new Error('No handle provided');
    log(`=== IG Circle Scraper: @${targetHandle} ===`);

    const onProfile = await ensureOnProfile();
    if (!onProfile) {
      // Page is navigating; popup.js will re-inject after load.
      window.__IG_SCRAPE_RUNNING = false;
      return;
    }

    // --- private profile detection ---
    if (isPrivateProfile()) {
      log(`[SKIP] @${targetHandle} is private — skipping`);
      sendStats({ phase: 'private', handle: targetHandle });
      chrome.runtime.sendMessage({ type: 'private', handle: targetHandle });
      window.__IG_SCRAPE_RUNNING = false;
      return;
    }

    // --- followers ---
    sendStats({ phase: 'followers', handle: targetHandle });
    let dialog = await openList('followers');
    const followers = await scrollAndScrape('followers', dialog);
    log(`Collected ${followers.length} followers`);
    closeAnyDialog();
    await delay(1200);
    await saveList('followers', followers);

    if (shouldStop()) throw new Error('stopped');

    // --- following ---
    sendStats({ phase: 'following' });
    dialog = await openList('following');
    const following = await scrollAndScrape('following', dialog);
    log(`Collected ${following.length} following`);
    closeAnyDialog();
    await delay(800);
    await saveList('following', following);

    sendStats({ phase: 'done' });
    log('=== DONE ===');
    chrome.runtime.sendMessage({ type: 'complete' });
  } catch (err) {
    log(`[ERR] ${err.message}`);
    console.error(err);
    if (err.message === 'stopped') {
      chrome.runtime.sendMessage({ type: 'stopped' });
    } else {
      chrome.runtime.sendMessage({ type: 'error', text: err.message });
    }
  } finally {
    window.__IG_SCRAPE_RUNNING = false;
  }
})();
