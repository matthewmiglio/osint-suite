const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const handleInput = document.getElementById('handleInput');
const downloadPics = document.getElementById('downloadPics');
const terminal = document.getElementById('terminal');
const statPhase = document.getElementById('statPhase');
const statFollowers = document.getElementById('statFollowers');
const statFollowing = document.getElementById('statFollowing');
const statElapsed = document.getElementById('statElapsed');
const statQueue = document.getElementById('statQueue');
const statHandle = document.getElementById('statHandle');

let currentTabId = null;
let timerStartedAt = null;
let timerElapsedBase = 0;

// Queue state (also mirrored to background so popup can reopen mid-run)
let queue = [];
let totalQueue = 0;
let currentHandle = null;
let abort = false;

function formatTime(s) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}
function getElapsed() {
  let s = timerElapsedBase;
  if (timerStartedAt) s += (Date.now() - timerStartedAt) / 1000;
  return s;
}
function updateTimer() { statElapsed.textContent = formatTime(getElapsed()); }
setInterval(updateTimer, 1000);

function addLog(text, type = 'info') {
  const p = document.createElement('p');
  p.className = `log-line log-${type}`;
  p.textContent = text;
  terminal.appendChild(p);
  terminal.scrollTop = terminal.scrollHeight;
}
function clearTerminal() { terminal.innerHTML = ''; }
function updateStats(s) {
  if (!s) return;
  if (s.phase) statPhase.textContent = s.phase;
  if (typeof s.followers === 'number') statFollowers.textContent = s.followers;
  if (typeof s.following === 'number') statFollowing.textContent = s.following;
  if (s.handle) statHandle.textContent = s.handle;
}
function updateQueueStat() {
  if (totalQueue === 0) { statQueue.textContent = '-'; return; }
  const done = totalQueue - queue.length - (currentHandle ? 1 : 0);
  statQueue.textContent = `${done}/${totalQueue}` + (currentHandle ? ` · now: ${currentHandle}` : '');
}

// Restore state from background on popup open
chrome.runtime.sendMessage({ type: 'getState' }, (state) => {
  if (!state) return;
  if (state.queue) {
    queue = state.queue.slice();
    totalQueue = state.totalQueue || queue.length;
    currentHandle = state.currentHandle || null;
  }
  if (state.stats && state.stats.handle) statHandle.textContent = state.stats.handle;
  if (state.running) {
    startBtn.disabled = true;
    startBtn.style.display = 'none';
    stopBtn.style.display = 'block';
  }
  updateStats(state.stats);
  updateQueueStat();
  timerStartedAt = state.startedAt;
  timerElapsedBase = state.elapsedBeforePause || 0;
  updateTimer();
  clearTerminal();
  for (const line of (state.logs || [])) {
    const type = line.startsWith('[ERR]') || line.startsWith('[SKIP]') ? 'err' : 'info';
    addLog(line, type);
  }
});

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'log') {
    const t = message.text;
    const type = t.startsWith('[ERR]') || t.startsWith('[SKIP]') ? 'err' : 'info';
    addLog(t, type);
  } else if (message.type === 'stats') {
    updateStats(message.stats);
  } else if (message.type === 'complete') {
    addLog(`=== COMPLETE: @${currentHandle || '?'} ===`, 'info');
    currentHandle = null;
    updateQueueStat();
    runNext();
  } else if (message.type === 'private') {
    addLog(`[SKIP] @${currentHandle} is private — skipping`, 'err');
    currentHandle = null;
    updateQueueStat();
    runNext();
  } else if (message.type === 'stopped') {
    addLog('=== STOPPED ===', 'err');
    abort = true;
    queue = [];
    currentHandle = null;
    updateQueueStat();
    finishUI();
  } else if (message.type === 'error') {
    addLog('[ERR] ' + message.text, 'err');
    currentHandle = null;
    updateQueueStat();
    runNext();
  }
});

function finishUI() {
  if (timerStartedAt) {
    timerElapsedBase += (Date.now() - timerStartedAt) / 1000;
    timerStartedAt = null;
  }
  updateTimer();
  startBtn.disabled = false;
  startBtn.style.display = 'block';
  stopBtn.style.display = 'none';
  statPhase.textContent = 'idle';
  chrome.runtime.sendMessage({ type: 'queueDone' });
}

async function runHandle(handle) {
  currentHandle = handle;
  updateQueueStat();
  addLog(`\n--- Starting @${handle} (${totalQueue - queue.length}/${totalQueue}) ---`, 'info');

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTabId = tab.id;

  const targetUrl = `https://www.instagram.com/${handle}/`;
  addLog(`Navigating to ${targetUrl}`, 'info');
  await chrome.tabs.update(tab.id, { url: targetUrl });
  await new Promise((resolve) => {
    const listener = (tabId, info) => {
      if (tabId === tab.id && info.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    };
    chrome.tabs.onUpdated.addListener(listener);
  });
  await new Promise(r => setTimeout(r, 1500));

  chrome.runtime.sendMessage({
    type: 'started', handle, queue, totalQueue, currentHandle
  });

  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (handle, dlPics) => {
        window.__IG_SCRAPE_CONFIG = { handle, downloadPics: dlPics };
        window.__IG_SCRAPE_STOP = false;
        window.__IG_SCRAPE_RUNNING = false;
      },
      args: [handle, downloadPics.checked]
    });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ['content.js']
    });
  } catch (err) {
    addLog('[ERR] ' + err.message, 'err');
    currentHandle = null;
    runNext();
  }
}

function runNext() {
  if (abort) { finishUI(); return; }
  if (queue.length === 0) {
    addLog(`\n=== ALL DONE (${totalQueue} processed) ===`, 'info');
    finishUI();
    return;
  }
  const next = queue.shift();
  updateQueueStat();
  setTimeout(() => runHandle(next), 1500);
}

startBtn.addEventListener('click', () => {
  const raw = handleInput.value.trim();
  if (!raw) { addLog('[ERR] Enter at least one username', 'err'); return; }
  const handles = raw
    // Split on whitespace OR comma — handles newline-, comma-, space- or mixed-separated input
    .split(/[\s,]+/)
    .map(h => h.trim()
                .replace(/^@/, '')
                .replace(/^https?:\/\/(www\.)?instagram\.com\//, '')
                .replace(/\/.*$/, ''))
    .filter(Boolean);
  // Dedupe while preserving order
  const seen = new Set();
  const dedup = handles.filter(h => seen.has(h) ? false : (seen.add(h), true));
  if (dedup.length === 0) { addLog('[ERR] No valid handles', 'err'); return; }

  abort = false;
  queue = dedup.slice();
  totalQueue = queue.length;
  currentHandle = null;

  startBtn.disabled = true;
  startBtn.style.display = 'none';
  stopBtn.style.display = 'block';
  clearTerminal();
  addLog(`Queue: ${totalQueue} handle${totalQueue === 1 ? '' : 's'} — ${dedup.join(', ')}`, 'info');
  updateQueueStat();

  timerStartedAt = Date.now();
  timerElapsedBase = 0;
  updateTimer();
  runNext();
});

stopBtn.addEventListener('click', async () => {
  abort = true;
  queue = [];
  updateQueueStat();
  addLog('Stopping...', 'info');
  let tabId = currentTabId;
  if (!tabId) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    tabId = tab.id;
  }
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: () => { window.__IG_SCRAPE_STOP = true; }
    });
  } catch (err) {
    addLog('[ERR] Failed to stop: ' + err.message, 'err');
  }
  finishUI();
});

document.getElementById('copyLogBtn').addEventListener('click', () => {
  const lines = terminal.querySelectorAll('.log-line');
  const text = Array.from(lines).map(p => p.textContent).join('\n');
  navigator.clipboard.writeText(text).then(() => {
    const b = document.getElementById('copyLogBtn');
    b.textContent = 'Copied!';
    setTimeout(() => { b.textContent = 'Copy Log'; }, 1500);
  });
});
