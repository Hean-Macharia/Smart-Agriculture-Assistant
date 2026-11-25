const DB_NAME = "shambalink-offline";
const DB_VERSION = 1;
const STORES = { snapshots: "snapshots", queue: "queue", drafts: "drafts" };

function openDatabase() {
  if (!globalThis.indexedDB) return Promise.reject(new Error("This browser does not support offline storage."));
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORES.snapshots)) db.createObjectStore(STORES.snapshots, { keyPath: "key" });
      if (!db.objectStoreNames.contains(STORES.queue)) {
        const queue = db.createObjectStore(STORES.queue, { keyPath: "operationId" });
        queue.createIndex("ownerId", "ownerId");
        queue.createIndex("createdAt", "createdAt");
      }
      if (!db.objectStoreNames.contains(STORES.drafts)) {
        const drafts = db.createObjectStore(STORES.drafts, { keyPath: "draftId" });
        drafts.createIndex("ownerId", "ownerId");
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Could not open offline storage."));
  });
}

async function withStore(storeName, mode, action) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, mode);
    const store = tx.objectStore(storeName);
    let result;
    try { result = action(store); } catch (error) { db.close(); reject(error); return; }
    tx.oncomplete = () => {
      const value = result && typeof result.then === "function" ? result : result?.result;
      Promise.resolve(value).then((resolved) => { db.close(); resolve(resolved); }, (error) => { db.close(); reject(error); });
    };
    tx.onerror = () => { db.close(); reject(tx.error || new Error("Offline storage transaction failed.")); };
    tx.onabort = () => { db.close(); reject(tx.error || new Error("Offline storage transaction was cancelled.")); };
  });
}

const allFrom = (store) => new Promise((resolve, reject) => {
  const request = store.getAll();
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => reject(request.error);
});

export const makeId = () => globalThis.crypto?.randomUUID?.() || `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export async function saveSnapshot(ownerId, name, data) {
  const savedAt = new Date().toISOString();
  await withStore(STORES.snapshots, "readwrite", (store) => store.put({ key: `${ownerId}:${name}`, ownerId, name, data, savedAt }));
  return savedAt;
}

export async function getSnapshot(ownerId, name) {
  const record = await withStore(STORES.snapshots, "readonly", (store) => store.get(`${ownerId}:${name}`));
  return record || null;
}

export async function enqueueOperation({ operationId = makeId(), ownerId, type, localId, resourceId = null, payload, baseUpdatedAt = null, dependsOn = null }) {
  const record = {
    operationId, ownerId, type, localId, resourceId, payload, baseUpdatedAt, dependsOn,
    status: "pending", attempts: 0, nextAttemptAt: 0, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), lastError: null,
  };
  await withStore(STORES.queue, "readwrite", (store) => store.add(record));
  return record;
}

export async function listQueue(ownerId) {
  const records = await withStore(STORES.queue, "readonly", allFrom);
  return records.filter((item) => item.ownerId === ownerId).sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function updateOperation(operationId, changes) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORES.queue, "readwrite");
    const store = tx.objectStore(STORES.queue);
    const request = store.get(operationId);
    request.onsuccess = () => {
      if (request.result) store.put({ ...request.result, ...changes, updatedAt: new Date().toISOString() });
    };
    tx.oncomplete = () => { db.close(); resolve(); };
    tx.onerror = () => { db.close(); reject(tx.error || new Error("Could not update offline operation.")); };
  });
}

export async function saveListingDraft(ownerId, payload, images = []) {
  const record = { draftId: makeId(), ownerId, payload, images, status: "draft", createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() };
  await withStore(STORES.drafts, "readwrite", (store) => store.add(record));
  return record;
}

export async function listListingDrafts(ownerId) {
  const records = await withStore(STORES.drafts, "readonly", allFrom);
  return records.filter((item) => item.ownerId === ownerId).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export async function deleteListingDraft(draftId) {
  return withStore(STORES.drafts, "readwrite", (store) => store.delete(draftId));
}

export async function syncQueue(ownerId, send, { now = Date.now() } = {}) {
  const records = await listQueue(ownerId);
  const summary = { synced: 0, retrying: 0, conflicts: 0, blocked: false, failed: 0 };
  const serverIds = new Map(records.filter((item) => item.serverId).map((item) => [item.localId, item.serverId]));
  for (const record of records) {
    if (!["pending", "retrying", "blocked_auth", "blocked_dependency", "syncing"].includes(record.status)) continue;
    if (record.nextAttemptAt > now && record.status !== "blocked_auth") { summary.retrying += 1; continue; }
    let url;
    let method = "POST";
    let body = record.payload;
    const headers = { "Idempotency-Key": record.operationId };

    if (record.type === "farm.create") url = "/farms";
    else if (record.type === "crop.create") {
      url = "/crops";
      if (record.dependsOn) {
        const parentServerId = serverIds.get(record.dependsOn);
        if (!parentServerId) {
          await updateOperation(record.operationId, { status: "blocked_dependency", lastError: "The farm record must sync before this crop." });
          summary.failed += 1;
          continue;
        }
        body = { ...body, farm_id: parentServerId };
      }
    } else if (record.type === "crop.update") {
      url = `/crops/${record.resourceId}`;
      method = "PATCH";
      headers["If-Match"] = `"${record.baseUpdatedAt}"`;
      delete headers["Idempotency-Key"];
    } else {
      await updateOperation(record.operationId, { status: "failed", lastError: "Unknown queued change." });
      summary.failed += 1;
      continue;
    }

    await updateOperation(record.operationId, { status: "syncing", lastError: null });
    try {
      const response = await send(url, { method, headers, body: JSON.stringify(body) });
      const serverId = response?.id || record.serverId;
      if (serverId) serverIds.set(record.localId, serverId);
      await updateOperation(record.operationId, { status: "synced", serverId, serverUpdatedAt: response?.updated_at || null, lastError: null });
      summary.synced += 1;
    } catch (error) {
      const attempts = record.attempts + 1;
      if (error.status === 401) {
        await updateOperation(record.operationId, { status: "blocked_auth", attempts, lastError: "Sign in again with the same account to sync this change." });
        summary.blocked = true;
        break;
      }
      if (error.status === 409) {
        await updateOperation(record.operationId, { status: "conflict", attempts, lastError: error.message || "This record changed on the server. Review both versions." });
        summary.conflicts += 1;
        continue;
      }
      if (error.status && error.status < 500) {
        await updateOperation(record.operationId, { status: "failed", attempts, lastError: error.message || "The server rejected this change." });
        summary.failed += 1;
        continue;
      }
      const delay = Math.min(15 * 60_000, 2 ** Math.min(attempts, 9) * 1000);
      await updateOperation(record.operationId, { status: "retrying", attempts, nextAttemptAt: now + delay, lastError: error.message || "Connection failed; this change is saved for retry." });
      summary.retrying += 1;
    }
  }
  return summary;
}

export function createLocalFarm(payload, localId) {
  return { ...payload, id: localId, is_active: true, pending_sync: true, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
}

export function createLocalCrop(payload, localId) {
  return { ...payload, id: localId, owner_id: null, is_active: true, pending_sync: true, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
}
