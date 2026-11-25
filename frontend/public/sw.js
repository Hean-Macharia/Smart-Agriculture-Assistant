const CACHE_PREFIX = "shambalink-shell-";
const CACHE_NAME = `${CACHE_PREFIX}v1`;
const SHELL = [
  "/",
  "/offline.html",
  "/manifest.webmanifest",
  "/icons/shambalink-192.png",
  "/icons/shambalink-180.png",
  "/icons/shambalink-512.png",
  "/icons/shambalink-maskable-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(SHELL);
    const manifestResponse = await fetch("/precache-assets.json", { cache: "no-store" });
    if (!manifestResponse.ok) throw new Error("Could not load the offline asset list.");
    const manifest = await manifestResponse.json();
    await cache.addAll(manifest.assets || []);
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME).map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  // Authenticated API responses are deliberately never stored in Cache Storage.
  const isApi = /^\/(auth|farmers|buyers|farms|crops|marketplace|orders|payments|escrow|payouts|transactions|deliveries|disputes|weather|advisories|market-prices|notifications|disease-detection|admin|pesticide-records|crop-planning|pest-knowledge|ussd|health)(\/|$)/.test(url.pathname);
  if (isApi || url.pathname === "/openapi.json") return;

  if (request.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        if (response.ok) (await caches.open(CACHE_NAME)).put("/", response.clone());
        return response;
      } catch {
        return (await caches.match(request)) || (await caches.match("/")) || (await caches.match("/offline.html"));
      }
    })());
    return;
  }

  if (["script", "style", "font", "image"].includes(request.destination)) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      const cached = await cache.match(request);
      if (cached) return cached;
      try {
        const response = await fetch(request);
        if (response.ok) await cache.put(request, response.clone());
        return response;
      } catch {
        return cached || Response.error();
      }
    })());
  }
});
