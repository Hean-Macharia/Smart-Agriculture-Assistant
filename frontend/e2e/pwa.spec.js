import { expect, test } from "@playwright/test";

const farm = {
  id: "64b000000000000000000071", owner_id: "64b000000000000000000011",
  name: "Saved Njoro Farm", county: "Nakuru", sub_county: "Njoro", location: "Mau Narok",
  size_acres: 3, soil_type: "Loam", irrigation_available: false, latitude: null, longitude: null,
  is_active: true, created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
};
const user = {
  id: "64b000000000000000000011", full_name: "Offline Test Farmer",
  email: "offline-farmer@example.test", phone: "+254712345678", role: "FARMER", is_active: true,
  created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
};
const list = (items = []) => ({ items, total: items.length, limit: 30, offset: 0 });

test("manifest and production app shell remain available in genuine browser offline mode", async ({ page }) => {
  await page.route("**/marketplace/products*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(list([])) }));
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: /Good food grows a stronger future/ })).toBeVisible();

  const manifestResponse = await page.request.get("/manifest.webmanifest");
  expect(manifestResponse.ok()).toBeTruthy();
  const manifest = await manifestResponse.json();
  expect(manifest.display).toBe("standalone");
  expect(manifest.icons.map((icon) => icon.sizes)).toContain("192x192");
  expect(manifest.icons.map((icon) => icon.sizes)).toContain("512x512");

  const assets = await page.request.get("/precache-assets.json");
  expect(assets.ok()).toBeTruthy();
  expect((await assets.json()).assets.some((asset) => asset.endsWith(".js"))).toBeTruthy();
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBeTruthy();

  await page.context().setOffline(true);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: /Good food grows a stronger future/ })).toBeVisible();
  const apiResult = await page.evaluate(async () => {
    try { return (await fetch("/health/ready")).status; }
    catch { return "network-unavailable"; }
  });
  expect(apiResult).toBe("network-unavailable");
});

test("a farm saved after a failed request survives reload and syncs once under the original account", async ({ browser }) => {
  // This workflow verifies IndexedDB queue persistence and mock API sync. The
  // other test independently verifies the service worker; blocking it here
  // lets Playwright intercept the API requests instead of a controlled page.
  const context = await browser.newContext({ serviceWorkers: "block", viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const farms = [farm];
  const crops = [];
  let createCalls = 0;
  let cropCreateCalls = 0;
  let failFarmCreate = true;
  let failCropCreate = true;
  await page.route("https://fonts.googleapis.com/**", (route) => route.fulfill({ status: 200, contentType: "text/css", body: "" }));
  await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== "http://127.0.0.1:4173") return route.continue();
    const { pathname } = url;
    const json = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (pathname === "/auth/login" && request.method() === "POST") {
      return json({ access_token: "volatile-browser-token", token_type: "bearer", expires_in: 1800, user });
    }
    if (pathname === "/marketplace/products" || pathname === "/marketplace/products/mine") return json(list([]));
    if (pathname === "/farms" && request.method() === "GET") return json(list(farms));
    if (pathname === "/farms" && request.method() === "POST") {
      if (failFarmCreate) return route.abort();
      createCalls += 1;
      expect(request.headers()["idempotency-key"]).toBeTruthy();
      const submitted = request.postDataJSON();
      const created = { ...farm, ...submitted, id: "64b000000000000000000072", updated_at: "2026-11-25T00:00:00Z" };
      farms.push(created);
      return json(created, 201);
    }
    if (pathname === "/crops" && request.method() === "POST") {
      if (failCropCreate) return route.abort();
      cropCreateCalls += 1;
      const submitted = request.postDataJSON();
      expect(submitted.farm_id).toBe("64b000000000000000000072");
      const created = { ...submitted, id: "64b000000000000000000073", owner_id: user.id, is_active: true, created_at: "2026-11-25T00:00:00Z", updated_at: "2026-11-25T00:00:00Z" };
      crops.push(created);
      return json(created, 201);
    }
    if (pathname === "/crops" && request.method() === "GET") return json(list(crops));
    if (pathname.startsWith("/orders") || pathname.startsWith("/advisories") || pathname.startsWith("/market-prices") || pathname.startsWith("/notifications")) return json(list([]));
    if (pathname.startsWith("/auth/")) return json({ detail: "Not authenticated" }, 401);
    return route.continue();
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Email address").fill(user.email);
  await page.getByLabel("Password").fill("Offline-Test-Password-123!");
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "My farm" }).click();
  await expect(page.getByText("Saved Njoro Farm")).toBeVisible();
  await page.getByRole("button", { name: "Add farm" }).click();
  await page.getByLabel("Farm name").fill("Offline Demo Farm");
  await page.getByRole("textbox", { name: "County", exact: true }).fill("Nakuru");
  await page.getByLabel("Sub-county").fill("Njoro");
  await page.getByLabel("Location").fill("Mau Narok");
  await page.getByLabel("Size (acres)").fill("2");
  await page.getByLabel("Soil type").fill("Loam");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Offline Demo Farm")).toBeVisible();
  await expect(page.getByText(/saved on device/).first()).toBeVisible();
  await page.getByRole("button", { name: "Add crop" }).click();
  await page.getByRole("dialog").getByRole("combobox", { name: "Farm" }).selectOption({ label: "Offline Demo Farm" });
  await page.getByLabel("Crop name").fill("Maize");
  await page.getByLabel("Planting date").fill("2026-10-01");
  await page.getByLabel("Quantity").fill("5");
  await page.getByLabel("Unit").fill("kg");
  await page.getByLabel("Growth notes").fill("Healthy seedlings");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Maize")).toBeVisible();
  await expect(page.getByText(/saved on device/).nth(1)).toBeVisible();

  await page.reload({ waitUntil: "domcontentloaded" });
  const savedQueue = await page.evaluate(async () => {
    const db = await new Promise((resolve, reject) => {
      const request = indexedDB.open("shambalink-offline");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const rows = await new Promise((resolve, reject) => {
      const request = db.transaction("queue", "readonly").objectStore("queue").getAll();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    db.close();
    return rows;
  });
  expect(savedQueue.some((entry) => entry.payload?.name === "Offline Demo Farm")).toBeTruthy();
  expect(savedQueue.some((entry) => entry.payload?.name === "Maize" && entry.dependsOn)).toBeTruthy();

  failFarmCreate = false;
  failCropCreate = false;
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Email address").fill(user.email);
  await page.getByLabel("Password").fill("Offline-Test-Password-123!");
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await expect.poll(() => createCalls).toBe(1);
  await expect.poll(() => cropCreateCalls).toBe(1);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "My farm" }).click();
  await expect(page.getByText("Offline Demo Farm")).toBeVisible();
  await expect(page.getByText(/saved on device/).first()).toHaveCount(0);
  expect(createCalls).toBe(1);
  await context.close();
});
