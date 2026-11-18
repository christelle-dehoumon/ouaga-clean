// IndexedDB minimal : files d'attente hors connexion (signalements citoyens, décisions de la brigade).
const DB_NAME = "ouaga-clean";
const DB_VERSION = 1;
const STORES = ["signalements", "decisions"];

let dbPromise = null;

function open() {
  if (!("indexedDB" in window)) return Promise.reject(new Error("Stockage local indisponible sur cet appareil."));
  dbPromise ??= new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      for (const s of STORES) if (!req.result.objectStoreNames.contains(s)) req.result.createObjectStore(s, { keyPath: "opId" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => { dbPromise = null; reject(req.error || new Error("Stockage local inaccessible.")); };
  });
  return dbPromise;
}

function tx(store, mode, fn) {
  return open().then((db) => new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const s = t.objectStore(store);
    let result;
    Promise.resolve(fn(s)).then((r) => { result = r; });
    t.oncomplete = () => resolve(result);
    t.onerror = () => reject(t.error);
    t.onabort = () => reject(t.error || new Error("Transaction annulée."));
  }));
}

const req2p = (req) => new Promise((resolve, reject) => { req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error); });

export const queue = {
  put: (store, item) => tx(store, "readwrite", (s) => req2p(s.put(item))),
  get: (store, id) => tx(store, "readonly", (s) => req2p(s.get(id))),
  all: (store) => tx(store, "readonly", (s) => req2p(s.getAll())),
  remove: (store, id) => tx(store, "readwrite", (s) => req2p(s.delete(id))),
};

/** Identifiant d'opération unique côté client. */
export function opId() {
  return (crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`);
}
