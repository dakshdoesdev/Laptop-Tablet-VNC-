const fs = require("fs");
const path = require("path");
const { chromium } = require("/home/dux/Work/tries/experiments/notebooklm-mcp-fix/node_modules/patchright");

const userDataDir = "/home/dux/.local/share/notebooklm-mcp/chrome_profile";
const executablePath = "/usr/bin/chromium";
const stateDir = "/home/dux/.local/share/notebooklm-mcp/browser_state";
const statePath = path.join(stateDir, "state.json");
const sessionPath = path.join(stateDir, "session.json");

async function main() {
  fs.mkdirSync(stateDir, { recursive: true });

  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: true,
    executablePath,
    args: [
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-dev-shm-usage",
    ],
  });

  const pages = context.pages();
  const page = pages.length ? pages[0] : await context.newPage();

  await page.goto("https://notebooklm.google.com", {
    waitUntil: "domcontentloaded",
    timeout: 120000,
  });

  await context.storageState({ path: statePath });

  const sessionStorageData = await page.evaluate(() => {
    const storage = {};
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i);
      if (key) storage[key] = sessionStorage.getItem(key) || "";
    }
    return JSON.stringify(storage);
  });

  fs.writeFileSync(sessionPath, sessionStorageData, "utf8");

  const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
  console.log(JSON.stringify({
    statePath,
    sessionPath,
    cookies: state.cookies?.length || 0,
    origins: state.origins?.length || 0,
    currentUrl: page.url(),
  }, null, 2));

  await context.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
