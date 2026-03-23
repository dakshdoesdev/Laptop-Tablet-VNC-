const fs = require("fs");
const path = require("path");
const { chromium } = require("/home/dux/Work/tries/experiments/notebooklm-mcp-fix/node_modules/patchright");

const outDir = "/home/dux/Work/tries/projects/vnc-dual-tablet-research-2026-03-21/artifacts";

async function getActiveStitchFrame(page) {
  for (let i = 0; i < 20; i++) {
    const frame = page.frames().find((f) => f.url().includes("app-companion-430619.appspot.com"));
    if (frame) return frame;
    await page.waitForTimeout(1000);
  }
  return null;
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    executablePath: "/usr/bin/chromium",
    args: ["--no-first-run", "--no-default-browser-check", "--disable-dev-shm-usage"],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    storageState: "/home/dux/.local/share/notebooklm-mcp/browser_state/state.json",
  });

  const page = await context.newPage();
  await page.goto("https://stitch.withgoogle.com", { waitUntil: "load", timeout: 120000 });
  await page.waitForTimeout(8000);

  let frame = await getActiveStitchFrame(page);
  if (!frame) throw new Error("stitch iframe missing");

  await frame.getByRole("button", { name: /Try now|Start designing/i }).first().click();
  await page.waitForTimeout(12000);

  frame = await getActiveStitchFrame(page);
  if (!frame) throw new Error("stitch iframe missing after click");

  const body = await frame.locator("body").innerText().catch(() => "");
  const buttons = await frame
    .getByRole("button")
    .evaluateAll((els) =>
      els
        .map((el) => ({
          text: (el.innerText || "").trim(),
          aria: el.getAttribute("aria-label") || "",
        }))
        .filter((x) => x.text || x.aria)
    )
    .catch(() => []);
  const inputs = await frame
    .locator("textarea,input")
    .evaluateAll((els) =>
      els.map((el) => ({
        tag: el.tagName.toLowerCase(),
        type: el.getAttribute("type") || "",
        placeholder: el.getAttribute("placeholder") || "",
        aria: el.getAttribute("aria-label") || "",
        value: el.value || "",
      }))
    )
    .catch(() => []);

  await page.screenshot({ path: path.join(outDir, "stitch-design-flow.png"), fullPage: true });

  console.log(
    JSON.stringify(
      {
        pageUrl: page.url(),
        frameUrl: frame.url(),
        body: body.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 160),
        buttons: buttons.slice(0, 80),
        inputs,
        screenshot: path.join(outDir, "stitch-design-flow.png"),
      },
      null,
      2
    )
  );

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
