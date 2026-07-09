// Saves images + per-photo JSON + index JSON into Downloads/{folder}/

let pendingFilename = null;

chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  if (pendingFilename) {
    const f = pendingFilename;
    pendingFilename = null;
    suggest({ filename: f, conflictAction: 'uniquify' });
  } else {
    suggest();
  }
});

function extFromUrl(url, fallback = 'jpg') {
  try {
    const u = new URL(url);
    const m = u.pathname.match(/\.([a-zA-Z0-9]{2,5})(?:$|[?#])/);
    if (m) return m[1].toLowerCase();
  } catch (_) {}
  return fallback;
}

async function blobToDataUrl(blob) {
  const buf = await blob.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let bin = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  const b64 = btoa(bin);
  const type = blob.type || 'application/octet-stream';
  return `data:${type};base64,${b64}`;
}

function startDownloadAndWait(url, filename) {
  pendingFilename = filename;
  return new Promise((resolve, reject) => {
    chrome.downloads.download({ url, conflictAction: 'uniquify', saveAs: false }, (id) => {
      if (chrome.runtime.lastError) {
        pendingFilename = null;
        return reject(new Error(chrome.runtime.lastError.message));
      }
      if (typeof id !== 'number') {
        pendingFilename = null;
        return reject(new Error('No download id'));
      }
      const timeout = setTimeout(() => {
        chrome.downloads.onChanged.removeListener(onChange);
        resolve(id);
      }, 30000);
      function onChange(delta) {
        if (delta.id !== id) return;
        if (delta.state && (delta.state.current === 'complete' || delta.state.current === 'interrupted')) {
          clearTimeout(timeout);
          chrome.downloads.onChanged.removeListener(onChange);
          resolve(id);
        }
      }
      chrome.downloads.onChanged.addListener(onChange);
    });
  });
}

async function saveImage(imageUrl, folder, slug, ext) {
  if (!imageUrl) return '';
  try {
    const res = await fetch(imageUrl);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const blob = await res.blob();
    const useExt = ext || extFromUrl(imageUrl, (blob.type.split('/')[1] || 'jpg').toLowerCase());
    const filename = `${folder}/${slug}/photo.${useExt}`;
    const url = await blobToDataUrl(blob);
    await startDownloadAndWait(url, filename);
    return filename;
  } catch (e) {
    console.error('Image save failed', e);
    return '';
  }
}

async function saveText(text, mime, filename) {
  const url = 'data:' + mime + ';base64,' + btoa(unescape(encodeURIComponent(text)));
  await startDownloadAndWait(url, filename);
}

function pad(n, w = 3) { return String(n).padStart(w, '0'); }

async function handleSave(payload) {
  const { folder, index, data } = payload;
  const slug = `photo-${pad(index)}`;
  const imagePath = await saveImage(data.imageUrl, folder, slug);
  const record = { ...data, imagePath, scrapedAt: new Date().toISOString() };
  await saveText(
    JSON.stringify(record, null, 2),
    'application/json;charset=utf-8',
    `${folder}/${slug}/data.json`
  );
  return { ok: true, slug, imagePath };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === 'SAVE_PHOTO') {
    handleSave(msg.payload)
      .then(result => sendResponse(result))
      .catch(err => sendResponse({ ok: false, error: String(err && err.message || err) }));
    return true;
  }
});
