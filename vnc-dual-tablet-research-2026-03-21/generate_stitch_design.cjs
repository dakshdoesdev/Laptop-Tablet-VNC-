const fs = require("fs");
const path = require("path");
const { chromium } = require("/home/dux/Work/tries/experiments/notebooklm-mcp-fix/node_modules/patchright");

const outDir = "/home/dux/Work/tries/projects/vnc-dual-tablet-research-2026-03-21/artifacts";
const prompt = [
  "Design a dark desktop control panel called Tablet VNC for Linux power users.",
  "Create a main dashboard with two profile cards: USB Tablet and Type-C Tablet.",
  "Each card should show mode, host or IP, port, refresh, fps, status, and actions for Start Stop Edit.",
  "Add a secondary settings screen with connection mode, host IP, port, resolution, refresh, fps, output position, workspace count, workspace start, and vertical alignment.",
  "Add a diagnostics drawer for output name, bind address, transport mode, wayvnc version, and warnings.",
  "Use graphite and muted gray panels with crisp borders and orange accents for active state.",
  "Make it feel sharp, technical, compact, and desktop-first."
].join(" ");

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
  await page.goto("https://stitch.withgoogle.com/?pli=1", { waitUntil: "load", timeout: 120000 });
  await page.waitForTimeout(12000);

  let frame = page.frames().find((f) => f.url().includes("app-companion-430619.appspot.com"));
  if (!frame) throw new Error("no stitch frame");

  const editor = frame.locator('[role="textbox"]').first();
  await editor.click();
  await page.keyboard.type(prompt, { delay: 8 });
  await page.waitForTimeout(2000);

  const generate = frame.getByRole("button", { name: "Generate designs" }).first();
  await generate.click();
  await page.waitForTimeout(70000);

  frame = page.frames().find((f) => f.url().includes("app-companion-430619.appspot.com")) || frame;

  const body = await frame.locator("body").innerText().catch(() => "");
  const buttons = await frame.getByRole("button").evaluateAll((els) =>
    els
      .map((el) => ({
        text: (el.innerText || "").trim(),
        aria: el.getAttribute("aria-label") || "",
      }))
      .filter((x) => x.text || x.aria)
  ).catch(() => []);

  await page.screenshot({ path: path.join(outDir, "stitch-generated.png"), fullPage: true });
  fs.writeFileSync(path.join(outDir, "stitch-generated-body.txt"), body);

  console.log(JSON.stringify({
    pageUrl: page.url(),
    frameUrl: frame.url(),
    body: body.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 220),
    buttons: buttons.slice(0, 100),
    screenshot: path.join(outDir, "stitch-generated.png"),
  }, null, 2));

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
