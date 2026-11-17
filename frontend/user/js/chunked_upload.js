const CHUNK_SIZE = 5 * 1024 * 1024;
const MAX_RETRY = 5;
const DB_NAME = 'ai_interview_uploads';
const STORE = 'blobs';

function basePath() {
  const path = window.location.pathname || '';
  return path === '/interview' || path.startsWith('/interview/') ? '/interview' : '';
}

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function stashBlob(sessionId, blob) {
  try {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(blob, sessionId);
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
  } catch (error) {
    console.warn('[upload] blob stash skipped', error);
  }
}

async function dropBlob(sessionId) {
  try {
    const db = await openDb();
    await new Promise((resolve) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).delete(sessionId);
      tx.oncomplete = resolve;
    });
  } catch (error) {
    console.warn('[upload] blob cleanup skipped', error);
  }
}

async function withRetry(task, attempt = 0) {
  try {
    return await task();
  } catch (error) {
    if (attempt >= MAX_RETRY) throw error;
    const delay = 1000 * Math.pow(2, attempt);
    await new Promise((resolve) => setTimeout(resolve, delay));
    return withRetry(task, attempt + 1);
  }
}

export async function uploadInChunks({ sessionId, blob, onProgress = () => {} }) {
  await stashBlob(sessionId, blob);
  const totalChunks = Math.ceil(blob.size / CHUNK_SIZE) || 1;

  const sessionResponse = await fetch(`${basePath()}/api/user/upload/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, total_chunks: totalChunks, chunk_size: CHUNK_SIZE }),
  });
  const session = await sessionResponse.json();
  if (session.status !== 'success') throw new Error(session.message || '创建上传任务失败');

  const uploadId = session.upload_id;
  let sent = 0;

  for (let index = 0; index < totalChunks; index += 1) {
    const start = index * CHUNK_SIZE;
    const chunk = blob.slice(start, start + CHUNK_SIZE);
    await withRetry(async () => {
      const response = await fetch(`${basePath()}/api/user/upload/chunk?upload_id=${uploadId}&index=${index}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: chunk,
      });
      const data = await response.json();
      if (data.status !== 'success') throw new Error(data.message || '分片上传失败');
      return data;
    });
    sent += 1;
    onProgress(Math.round((sent / totalChunks) * 100));
  }

  const completeResponse = await fetch(`${basePath()}/api/user/upload/complete?upload_id=${uploadId}`, {
    method: 'POST',
  });
  const done = await completeResponse.json();
  if (done.status === 'success') await dropBlob(sessionId);
  return done;
}
