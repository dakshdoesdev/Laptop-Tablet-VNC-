const fs = require("fs");
const path = require("path");
const { chromium } = require("/home/dux/Work/tries/experiments/notebooklm-mcp-fix/node_modules/patchright");

const executablePath = "/usr/bin/chromium";
const statePath = "/home/dux/.local/share/notebooklm-mcp/browser_state/state.json";
const notebookUrl = "https://notebooklm.google.com/notebook/1d825772-0d6a-4d9b-b496-13f33aa2cde6";
const outDir = "/home/dux/Work/tries/projects/vnc-dual-tablet-research-2026-03-21/artifacts";
const question = "Based on the uploaded source, what is the recommended architecture and default configuration for a Hyprland + wayvnc dual-tablet display manager that supports one ADB-capable tablet and one manual-host/IP tablet, while keeping low latency? Return a concise implementation summary with UI recommendations and key failure states.";

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
  await page.goto(notebookUrl, { waitUntil: "networkidle", timeout: 120000 });
  await page.waitForTimeout(3000);

  const queryBox = page.locator('textarea[aria-label="Query box"]').first();
  await queryBox.fill(question);
  await page.getByRole("button", { name: "Submit" }).first().click();

  const responseLocator = page.locator('div[role="article"], .response-markdown, .markdown, .model-response').last();
  await responseLocator.waitFor({ state: "visible", timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(12000);

  const bodyText = await page.locator("body").innerText();
  const lines = bodyText.split("\n").map((x) => x.trim()).filter(Boolean);
  const start = lines.findIndex((x) => x.includes("recommended architecture") || x.includes("default configuration") || x.includes("implementation summary"));
  const answerLines = start >= 0 ? lines.slice(start, Math.min(lines.length, start + 80)) : lines.slice(Math.max(0, lines.length - 80));
  const answer = answerLines.join("\n");

  fs.writeFileSync(path.join(outDir, "notebooklm-answer.txt"), answer + "\n");
  await page.screenshot({ path: path.join(outDir, "notebooklm-answer.png"), fullPage: true });

  console.log(JSON.stringify({
    notebookUrl,
    answer,
    screenshot: path.join(outDir, "notebooklm-answer.png"),
  }, null, 2));

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
