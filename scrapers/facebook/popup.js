const status = document.getElementById('status');
const folderEl = document.getElementById('folder');
const maxEl = document.getElementById('maxPhotos');
const delayEl = document.getElementById('delay');
const startBtn = document.getElementById('start');
const stopBtn = document.getElementById('stop');
const singleBtn = document.getElementById('single');

function setStatus(msg, cls) {
  status.textContent = msg;
  status.className = cls || 'muted';
}

async function getTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/facebook\.com/i.test(tab.url || '')) {
    setStatus('not on facebook.com', 'err');
    return null;
  }
  return tab;
}

async function ensureContent(tab) {
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
  } catch (e) {}
}

startBtn.addEventListener('click', async () => {
  const tab = await getTab();
  if (!tab) return;
  await ensureContent(tab);
  setStatus('starting walk...');
  const folder = (folderEl.value || 'fb-scrape').trim();
  const maxPhotos = parseInt(maxEl.value, 10) || 0;
  const delayMs = parseInt(delayEl.value, 10) || 1500;
  try {
    const res = await chrome.tabs.sendMessage(tab.id, { type: 'WALK', folder, maxPhotos, delayMs });
    if (res && res.ok) setStatus(`done — ${res.count} photos scraped`, 'ok');
    else setStatus(`failed: ${res && res.error || 'unknown'}`, 'err');
  } catch (e) {
    setStatus('error: ' + String(e.message || e), 'err');
  }
});

stopBtn.addEventListener('click', async () => {
  const tab = await getTab();
  if (!tab) return;
  await ensureContent(tab);
  try {
    await chrome.tabs.sendMessage(tab.id, { type: 'STOP' });
    setStatus('stop requested');
  } catch (e) {}
});

singleBtn.addEventListener('click', async () => {
  const tab = await getTab();
  if (!tab) return;
  await ensureContent(tab);
  setStatus('scraping one...');
  const folder = (folderEl.value || 'fb-scrape').trim();
  try {
    const res = await chrome.tabs.sendMessage(tab.id, { type: 'SCRAPE_ONE', folder });
    if (res && res.ok) setStatus('saved 1 photo', 'ok');
    else setStatus(`failed: ${res && res.error || 'unknown'}`, 'err');
  } catch (e) {
    setStatus('error: ' + String(e.message || e), 'err');
  }
});

// Live progress
chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === 'PROGRESS') setStatus(msg.text);
});
