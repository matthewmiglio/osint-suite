// Background service worker
// - Holds run state so popup can reopen mid-scrape and resume display
// - Receives scraped data and triggers downloads to ig-scrape-{handle}/...

let state = {
  running: false,
  logs: [],
  stats: { phase: 'idle', followers: 0, followersTotal: 0, following: 0, followingTotal: 0, handle: '' },
  startedAt: null,
  elapsedBeforePause: 0,
  // Batch queue state — mirrored from popup so it survives popup-close
  queue: [],
  totalQueue: 0,
  currentHandle: null
};

// Track filenames we asked for, keyed by download URL. The downloads.onDeterminingFilename
// listener fires after the download starts and lets us force the suggested filename even
// when the source is a data: URL (which otherwise gets named "download.json").
const pendingFilenames = new Map();
chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  const forced = pendingFilenames.get(item.url);
  if (forced) {
    pendingFilenames.delete(item.url);
    suggest({ filename: forced, conflictAction: 'overwrite' });
  } else {
    suggest();
  }
});

function pushLog(text) {
  state.logs.push(text);
  if (state.logs.length > 1000) state.logs.shift();
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'log') {
    pushLog(message.text);
  } else if (message.type === 'stats') {
    Object.assign(state.stats, message.stats);
  } else if (message.type === 'started') {
    state.running = true;
    if (state.currentHandle !== message.handle) state.logs = [];
    state.stats = { phase: 'starting', followers: 0, followersTotal: 0, following: 0, followingTotal: 0, handle: message.handle || '' };
    state.startedAt = state.startedAt || Date.now();
    state.queue = message.queue || [];
    state.totalQueue = message.totalQueue || state.queue.length;
    state.currentHandle = message.currentHandle || message.handle || null;
  } else if (message.type === 'private') {
    // Mid-queue: a profile was private. Stay running so the popup can advance.
    pushLog(`[SKIP] @${message.handle || state.currentHandle} is private`);
  } else if (message.type === 'queueDone') {
    if (state.startedAt) {
      state.elapsedBeforePause += (Date.now() - state.startedAt) / 1000;
      state.startedAt = null;
    }
    state.running = false;
    state.queue = [];
    state.currentHandle = null;
  } else if (message.type === 'stopped' || message.type === 'error') {
    if (state.startedAt) {
      state.elapsedBeforePause += (Date.now() - state.startedAt) / 1000;
      state.startedAt = null;
    }
    state.running = false;
  } else if (message.type === 'complete') {
    // Per-handle complete during a batch. Don't tear down running until queueDone.
  } else if (message.type === 'getState') {
    sendResponse({ ...state });
    return true;
  } else if (message.type === 'saveData') {
    // message: { handle, filename, data }
    const json = JSON.stringify(message.data, null, 2);
    const dataUrl = 'data:application/json;charset=utf-8,' + encodeURIComponent(json);
    const safeHandle = (message.handle || 'unknown').replace(/[<>:"/\\|?*]/g, '');
    const safeFile = String(message.filename || 'data.json').replace(/[<>:"/\\|?*]/g, '');
    const path = `${safeHandle}-${safeFile}`;
    // Pre-register the desired filename so onDeterminingFilename can force it
    // (data: URLs otherwise default to "download.json" regardless of the
    // `filename` we pass to chrome.downloads.download).
    pendingFilenames.set(dataUrl, path);
    chrome.downloads.download({
      url: dataUrl,
      filename: path,
      conflictAction: 'overwrite',
      saveAs: false
    }, (downloadId) => {
      if (chrome.runtime.lastError) {
        sendResponse({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        sendResponse({ ok: true, downloadId, path });
      }
    });
    return true;
  } else if (message.type === 'saveImage') {
    // message: { handle, subdir, name, url }
    const safeHandle = (message.handle || 'unknown').replace(/[<>:"/\\|?*]/g, '');
    const safeName = (message.name || 'img').replace(/[<>:"/\\|?*]/g, '');
    const safeSubdir = String(message.subdir || 'pics').replace(/[<>:"/\\|?*]/g, '');
    const ext = (message.url.match(/\.(jpg|jpeg|png|webp|gif)(\?|$)/i) || [, 'jpg'])[1].toLowerCase();
    // Images come from real CDN URLs so subfolder paths usually work — but flatten to match JSON convention.
    const path = `${safeHandle}-${safeSubdir}-${safeName}.${ext}`;
    chrome.downloads.download({
      url: message.url,
      filename: path,
      conflictAction: 'overwrite',
      saveAs: false
    }, (downloadId) => {
      if (chrome.runtime.lastError) {
        sendResponse({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        sendResponse({ ok: true, downloadId });
      }
    });
    return true;
  }
});
