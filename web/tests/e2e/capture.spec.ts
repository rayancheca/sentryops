import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

/**
 * Drives the seeded SentryOps stack and captures the golden-path screenshots
 * committed to docs/img and embedded in the README. Run with `make capture`
 * (the API on :8000 and the web app on :3100 must be up and seeded).
 */

const OUT = path.resolve(process.cwd(), "..", "docs", "img");
const API = process.env.CAPTURE_API_URL || "http://localhost:8000";
const ADMIN = { email: "admin@sentryops.local", password: "admin12345" };

fs.mkdirSync(OUT, { recursive: true });
const shot = (name: string) => path.join(OUT, name);

async function settleAndShoot(page: Page, route: string, name: string): Promise<void> {
  await page.goto(route, { waitUntil: "domcontentloaded" });
  // The operator UI keeps polling/animating, so networkidle never settles.
  // A fixed delay is enough: the local API answers in milliseconds.
  await page.waitForTimeout(2200);
  await page.screenshot({ path: shot(name) });
}

test("capture golden-path screenshots", async ({ page }) => {
  // 1) Login (pre-auth state)
  await page.goto("/login");
  await page.waitForLoadState("load").catch(() => {});
  await page.waitForTimeout(600);
  await page.screenshot({ path: shot("01-login.png") });

  // Authenticate (resilient to exact field markup: first input = email, second = password)
  const inputs = page.locator("input");
  await inputs.nth(0).fill(ADMIN.email);
  await inputs.nth(1).fill(ADMIN.password);
  const submit = page.locator('button[type="submit"]').first();
  if (await submit.count()) await submit.click();
  else await inputs.nth(1).press("Enter");
  await page.waitForURL(/dashboard/, { timeout: 25_000 }).catch(() => {});
  await page.waitForLoadState("load").catch(() => {});

  const token = await page.evaluate(() => window.localStorage.getItem("sentryops_token"));
  expect(token, "login should store an access token").toBeTruthy();

  // Resolve concrete ids for the detail pages via the API.
  const apiGet = (p: string) =>
    page.evaluate(
      async ([base, path, tok]) => {
        const r = await fetch(`${base}/api/v1${path}`, {
          headers: { Authorization: `Bearer ${tok}` },
        });
        return r.json();
      },
      [API, p, token] as const,
    );

  const openInc = await apiGet("/incidents?status=open&limit=1");
  const incidentId: string | undefined = openInc?.data?.items?.[0]?.id;
  const assetList = await apiGet("/assets?limit=100");
  const items: Array<{ id: string; name: string }> = assetList?.data?.items ?? [];
  const asset =
    items.find((a) => a.name === "postgres-primary") ??
    items.find((a) => a.name === "web-app-01") ??
    items[0];

  // 2) The four pillars + the AI triage showcase
  await settleAndShoot(page, "/dashboard", "02-dashboard.png");
  await settleAndShoot(page, "/compliance", "03-compliance.png");
  await settleAndShoot(page, "/assets", "04-assets.png");
  if (asset) await settleAndShoot(page, `/assets/${asset.id}`, "05-asset-detail.png");
  await settleAndShoot(page, "/observability", "06-observability.png");
  await settleAndShoot(page, "/incidents", "07-incidents.png");
  if (incidentId) await settleAndShoot(page, `/incidents/${incidentId}`, "08-incident-triage.png");

  const written = fs.readdirSync(OUT).filter((f) => f.endsWith(".png"));
  console.log(`Captured ${written.length} screenshots to ${OUT}:`, written.sort().join(", "));
  expect(written.length).toBeGreaterThanOrEqual(6);
});
