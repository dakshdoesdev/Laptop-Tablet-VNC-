const { chromium } = require("/home/dux/Work/tries/experiments/notebooklm-mcp-fix/node_modules/patchright");

async function main() {
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

  const frame = page.frames().find((f) => f.url().includes("app-companion-430619.appspot.com"));
  if (!frame) throw new Error("no stitch frame");

  const editables = await frame
    .locator('[contenteditable="true"], textarea, input, [role="textbox"]')
    .evaluateAll((els) =>
      els.map((el) => ({
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute("role") || "",
        placeholder: el.getAttribute("placeholder") || "",
        aria: el.getAttribute("aria-label") || "",
        text: (el.innerText || "").trim(),
        value: el.value || "",
        classes: el.className || "",
      }))
    );

  const buttons = await frame
    .getByRole("button")
    .evaluateAll((els) =>
      els
        .map((el) => ({
          text: (el.innerText || "").trim(),
          aria: el.getAttribute("aria-label") || "",
          classes: el.className || "",
        }))
        .filter((x) => x.text || x.aria)
    );

  console.log(JSON.stringify({ editables, buttons: buttons.slice(0, 80) }, null, 2));
  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
