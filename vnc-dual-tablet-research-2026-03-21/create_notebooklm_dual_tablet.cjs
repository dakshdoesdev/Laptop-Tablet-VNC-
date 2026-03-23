const fs = require("fs");
const path = require("path");
const { chromium } = require("/home/dux/Work/tries/experiments/notebooklm-mcp-fix/node_modules/patchright");

const executablePath = "/usr/bin/chromium";
const statePath = "/home/dux/.local/share/notebooklm-mcp/browser_state/state.json";
const outDir = "/home/dux/Work/tries/projects/vnc-dual-tablet-research-2026-03-21/artifacts";
const sourceFile = "/home/dux/Work/tries/projects/vnc-dual-tablet-research-2026-03-21/notebooklm-source-pack.md";
const notebookTitle = "Dual Tablet VNC Manager";

async function main() {
  fs.mkdirSync(outDir, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    executablePath,
    args: [
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-dev-shm-usage",
    ],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    storageState: statePath,
  });
  const page = await context.newPage();
  await page.goto("https://notebooklm.google.com", { waitUntil: "networkidle", timeout: 120000 });

  await page.getByRole("button", { name: /Create new notebook|Create new/i }).first().click();
  await page.waitForLoadState("networkidle", { timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(1500);

  const [fileChooser] = await Promise.all([
    page.waitForEvent("filechooser", { timeout: 20000 }),
    page.getByRole("button", { name: /Upload files/i }).click(),
  ]);

  await fileChooser.setFiles(sourceFile);

  await page.waitForLoadState("networkidle", { timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(6000);

  const backdrop = page.locator(".cdk-overlay-backdrop");
  if (await backdrop.count()) {
    await backdrop.last().click({ force: true }).catch(() => {});
    await page.waitForTimeout(1000);
  }

  const titleInput = page.locator('input.title-input, input').first();
  await titleInput.fill("");
  await titleInput.fill(notebookTitle);
  await titleInput.press("Enter").catch(() => {});
  await page.waitForTimeout(1000);

  const url = page.url();
  const buttons = await page.getByRole("button").evaluateAll((els) =>
    els.map((el) => ({
      text: (el.innerText || "").trim(),
      aria: el.getAttribute("aria-label") || "",
      title: el.getAttribute("title") || "",
    })).filter((x) => x.text || x.aria || x.title)
  );

  await page.screenshot({ path: path.join(outDir, "notebooklm-created.png"), fullPage: true });
  fs.writeFileSync(path.join(outDir, "notebooklm-created-buttons.json"), JSON.stringify(buttons, null, 2));
  fs.writeFileSync(path.join(outDir, "created-notebook-url.txt"), `${url}\n`);

  console.log(JSON.stringify({
    title: notebookTitle,
    url,
    buttons: buttons.slice(0, 60),
    screenshot: path.join(outDir, "notebooklm-created.png"),
  }, null, 2));

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
