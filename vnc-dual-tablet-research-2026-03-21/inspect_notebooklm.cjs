const fs = require("fs");
const path = require("path");
const { chromium } = require("/home/dux/Work/tries/experiments/notebooklm-mcp-fix/node_modules/patchright");

const userDataDir = "/home/dux/.local/share/notebooklm-mcp/chrome_profile";
const executablePath = "/usr/bin/chromium";
const outDir = "/home/dux/Work/tries/projects/vnc-dual-tablet-research-2026-03-21/artifacts";

async function main() {
  fs.mkdirSync(outDir, { recursive: true });

  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: true,
    executablePath,
    args: [
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-dev-shm-usage",
    ],
    viewport: { width: 1440, height: 960 },
  });

  const page = context.pages()[0] || await context.newPage();
  await page.goto("https://notebooklm.google.com", { waitUntil: "networkidle", timeout: 120000 });
  await page.screenshot({ path: path.join(outDir, "notebooklm-home.png"), fullPage: true });

  const buttons = await page.getByRole("button").evaluateAll((els) =>
    els.map((el) => ({
      text: (el.innerText || "").trim(),
      aria: el.getAttribute("aria-label") || "",
      title: el.getAttribute("title") || "",
    })).filter((x) => x.text || x.aria || x.title)
  );

  const links = await page.getByRole("link").evaluateAll((els) =>
    els.map((el) => ({
      text: (el.innerText || "").trim(),
      href: el.getAttribute("href") || "",
      aria: el.getAttribute("aria-label") || "",
    })).filter((x) => x.text || x.aria)
  );

  const fileInputs = await page.locator('input[type="file"]').evaluateAll((els) =>
    els.map((el) => ({
      accept: el.getAttribute("accept") || "",
      multiple: el.hasAttribute("multiple"),
    }))
  );

  fs.writeFileSync(path.join(outDir, "notebooklm-home-buttons.json"), JSON.stringify(buttons, null, 2));
  fs.writeFileSync(path.join(outDir, "notebooklm-home-links.json"), JSON.stringify(links, null, 2));
  fs.writeFileSync(path.join(outDir, "notebooklm-home-file-inputs.json"), JSON.stringify(fileInputs, null, 2));

  console.log(JSON.stringify({
    url: page.url(),
    title: await page.title(),
    buttons: buttons.slice(0, 40),
    links: links.slice(0, 40),
    fileInputs,
    screenshot: path.join(outDir, "notebooklm-home.png"),
  }, null, 2));

  await context.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
