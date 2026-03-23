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

  const editor = frame.locator('[role="textbox"]').first();
  await editor.click();
  await page.keyboard.type(
    "Design a dark desktop control panel called Tablet VNC with two cards: USB Tablet and Type-C Tablet. Show start stop edit, host, port, refresh, fps, and diagnostics.",
    { delay: 10 }
  );
  await page.waitForTimeout(1500);

  const buttonState = await frame
    .getByRole("button", { name: "Generate designs" })
    .evaluate((el) => ({
      disabled: Boolean(el.disabled),
      ariaDisabled: el.getAttribute("aria-disabled"),
      classes: el.className,
      text: el.innerText,
      title: el.getAttribute("title") || "",
    }));

  console.log(JSON.stringify(buttonState, null, 2));
  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
