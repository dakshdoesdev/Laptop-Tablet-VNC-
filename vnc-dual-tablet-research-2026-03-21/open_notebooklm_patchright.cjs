const { chromium } = require("/home/dux/Work/tries/experiments/notebooklm-mcp-fix/node_modules/patchright");

const userDataDir = "/home/dux/.local/share/notebooklm-mcp/chrome_profile";
const executablePath = "/usr/bin/chromium";
const url = "https://notebooklm.google.com";

async function main() {
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    executablePath,
    args: [
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-dev-shm-usage",
    ],
    viewport: { width: 1440, height: 960 },
  });

  const existing = context.pages();
  const page = existing.length ? existing[0] : await context.newPage();
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 120000 });
  console.log(`Opened ${url} with MCP profile: ${userDataDir}`);
  console.log("Leave this terminal session running while you log in.");

  process.stdin.resume();
  process.stdin.on("data", async (chunk) => {
    const text = chunk.toString().trim().toLowerCase();
    if (text === "q" || text === "quit" || text === "exit") {
      await context.close();
      process.exit(0);
    }
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
