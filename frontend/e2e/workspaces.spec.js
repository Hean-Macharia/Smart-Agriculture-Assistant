import { expect, test } from "@playwright/test";

const product = {
  id: "64b000000000000000000091",
  farmer_id: "64b000000000000000000011",
  product_name: "Test Tomatoes",
  category: "Vegetables",
  description: "Fresh test tomatoes",
  quantity_available: 20,
  unit: "kg",
  price_per_unit_kes: 120,
  county: "Nakuru",
  sub_county: "Njoro",
  product_images: [],
  availability_status: "ACTIVE",
};

function makeUser(role) {
  return {
    id: `64b0000000000000000000${{ FARMER: "11", BUYER: "22", AGRICULTURAL_OFFICER: "33", ADMIN: "44" }[role]}`,
    full_name: "Browser Test User",
    email: `${role.toLowerCase()}@example.test`,
    phone: "+254712345678",
    role,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function listResponse(items = []) {
  return { items, total: items.length, limit: 30, offset: 0 };
}

async function installApiMocks(page, role) {
  const user = makeUser(role);
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== "http://127.0.0.1:5173") return route.continue();
    const path = url.pathname;
    const method = request.method();
    if (!/^\/(auth|farmers|buyers|farms|crops|marketplace|orders|payments|escrow|payouts|transactions|deliveries|disputes|weather|advisories|market-prices|notifications|disease-detection|admin|pesticide-records|crop-planning|pest-knowledge|ussd|media|health)(\/|$)/.test(path)) return route.continue();
    const json = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/auth/login" && method === "POST") {
      return json({ access_token: "browser-test-token", token_type: "bearer", expires_in: 1800, user });
    }
    if (path === "/auth/me") return json(user);
    if (path === "/marketplace/products" && method === "GET") return json(listResponse([product]));
    if (path === "/marketplace/products/images" && method === "POST") {
      return json({ url: "/media/products/0123456789abcdef0123456789abcdef.webp", content_type: "image/webp" }, 201);
    }
    if (path === "/marketplace/products" && method === "POST") {
      const body = request.postDataJSON();
      return json({ ...product, ...body, id: "64b000000000000000000099" }, 201);
    }
    if (path === "/notifications/preferences") {
      return json({ phone_number: user.phone, consented: false, consented_at: null, opted_out_at: null, language: "en", categories: [], phone_verified: false, consent_history: [] });
    }
    if (path === "/admin/overview") {
      return json({
        counts: {
          users: { farmer: 1, buyer: 1, agricultural_officer: 1, admin: 1 },
          products: { total: 1, active: 1, inactive: 0 },
          orders: { total: 0, pending: 0, completed: 0, cancelled: 0 },
          payments: { total: 0, successful: 0, pending: 0, failed: 0 },
          disease_reports: 0,
          pending_officer_reviews: 0,
          pending_pesticide_reviews: 0,
        },
        trends: {}, disease_by_crop: [], disease_by_condition: [], payment_statuses: [],
        order_statuses: [], marketplace_by_county: [],
      });
    }
    if (path === "/health") return json({ status: "ok", service: "ShambaLink test API" });
    if (path === "/health/ready") return json({ status: "ready", database: "connected" });
    if (method === "GET") return json(listResponse([]));
    return json({ status: "ok" });
  });
}

async function loginAs(page, role) {
  await installApiMocks(page, role);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Email address").fill(`${role.toLowerCase()}@example.test`);
  await page.getByLabel("Password").fill("BrowserOnly-TestPassword-123!");
  await page.getByRole("button", { name: "Sign in securely" }).click();
  if (role === "ADMIN") await expect(page.getByRole("heading", { name: /Good morning, Browser/ })).toBeVisible();
  else await expect(page.locator(".user-chip")).toContainText("Browser");
}

for (const [role, expectedHeading] of [
  ["FARMER", /Hello, Browser/],
  ["BUYER", /Hello, Browser/],
  ["AGRICULTURAL_OFFICER", /Hello, Browser/],
  ["ADMIN", /Good morning, Browser/],
]) {
  test(`${role} can sign in and reach its role dashboard`, async ({ page }) => {
    await loginAs(page, role);
    await expect(page.getByRole("heading", { name: expectedHeading })).toBeVisible();
    if (role === "ADMIN") await expect(page.getByText("Farmers", { exact: true })).toBeVisible();
    if (role === "AGRICULTURAL_OFFICER") {
      await page.getByRole("button", { name: "Officer desk" }).click();
      await expect(page.getByRole("heading", { name: "Officer desk." })).toBeVisible();
      await expect(page.getByText("Disease screening review queue")).toBeVisible();
    }
    if (role === "BUYER") {
      await page.getByRole("button", { name: "Marketplace" }).click();
      await expect(page.getByText("Test Tomatoes")).toBeVisible();
    }
  });
}

test("farmer can review SMS preferences and preview a listing image", async ({ page }) => {
  await loginAs(page, "FARMER");
  await page.locator(".user-chip").click();
  await expect(page.getByRole("heading", { name: "SMS information" })).toBeVisible();
  await expect(page.getByText(/not verified/)).toBeVisible();

  await page.getByRole("button", { name: "Marketplace" }).click();
  await page.getByRole("button", { name: /List produce/ }).click();
  await page.getByLabel(/Product photos/).setInputFiles({
    name: "tomato.png",
    mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=", "base64"),
  });
  await expect(page.locator(".listing-previews img")).toHaveCount(1);
  await page.getByLabel("Product name").fill("Browser Test Tomatoes");
  await page.locator(".dialog select[name='category']").selectOption("Vegetables");
  await page.getByLabel("Description").fill("Fresh tomatoes for browser workflow verification.");
  await page.getByLabel("Quantity").fill("5");
  await page.getByLabel("Unit").fill("kg");
  await page.getByLabel("Price (KES)").fill("120");
  await page.locator(".dialog input[name='county']").fill("Nakuru");
  await page.locator(".dialog input[name='sub_county']").fill("Njoro");
  await page.getByRole("button", { name: "Publish listing" }).click();
  await expect(page.getByText("Produce listed.")).toBeVisible();
});

test("disease screening results stay stacked and readable across screen sizes", async ({ page }) => {
  await loginAs(page, "FARMER");
  await page.route("**/disease-detection/predict", (route) => route.fulfill({
    status: 201,
    contentType: "application/json",
    body: JSON.stringify({
      id: "64b000000000000000000071", farmer_id: makeUser("FARMER").id,
      filename: "leaf-photo.png", content_type: "image/png", file_size_bytes: 1200,
      image_sha256: "a".repeat(64), predicted_label: "Tomato___Late_blight",
      confidence: 0.923, confidence_threshold: 0.6, is_uncertain: false,
      uncertainty_message: null, disclaimer: "Preliminary screening only.",
      created_at: "2026-11-25T12:00:00Z", case_status: "OPEN",
      review_requested_at: null, resolved_at: null, officer_reviews: [],
    }),
  }));
  await page.route("**/disease-detection/knowledge/**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      model_label: "Tomato___Late_blight", crop_name: "Tomato",
      display_name: "Tomato late blight screening result with a long responsive label",
      scientific_name: null,
      summary: "This example screening summary is intentionally long enough to wrap across narrow phone screens without covering the confidence result or guidance below it.",
      symptoms: ["Water-soaked leaf spots that may darken over time", "Pale growth around affected areas in humid conditions"],
      general_guidance: ["Take a clear follow-up photo in daylight", "Ask an agricultural officer to review the result before deciding what to do"],
      sources: [{ organization: "Example Agricultural Reference", title: "A long source title that should wrap within the result card rather than extend beyond the screen width", url: "https://example.test/disease", reference: "D-1" }],
      source_checked_at: "2026-11-25", review_state: "REFERENCE",
      guidance_status: "GENERAL", chemical_guidance_available: false,
      disclaimer: "This information is general guidance and is not a confirmed diagnosis or pesticide recommendation.",
    }),
  }));

  await page.getByRole("button", { name: "Crop health" }).click();
  await page.locator('input[name="image"]').setInputFiles({
    name: "leaf.png", mimeType: "image/png", buffer: Buffer.from("test image"),
  });
  await page.getByRole("button", { name: "Screen image" }).click();
  const result = page.locator(".prediction");
  await expect(result).toBeVisible();
  await expect(result).toContainText("92% model confidence");
  await expect(result).toContainText("What may be seen");

  for (const width of [375, 768, 1365]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    const container = await result.boundingBox();
    const children = await result.locator(":scope > *").all();
    const boxes = [];
    for (const child of children) {
      const box = await child.boundingBox();
      if (box) boxes.push(box);
    }
    for (let index = 0; index < boxes.length; index += 1) {
      expect(boxes[index].x).toBeGreaterThanOrEqual(container.x - 1);
      expect(boxes[index].x + boxes[index].width).toBeLessThanOrEqual(container.x + container.width + 1);
      if (index > 0) expect(boxes[index].y).toBeGreaterThanOrEqual(boxes[index - 1].y + boxes[index - 1].height - 1);
    }
  }
});

test("landing and workspace fit mobile and desktop viewports without horizontal overflow", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  for (const width of [375, 768, 1365]) {
    await page.setViewportSize({ width, height: 812 });
    await expect(page.getByRole("heading", { name: /Good food grows a stronger future/ })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  }
  await loginAs(page, "FARMER");
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.locator("#workspace-navigation")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
