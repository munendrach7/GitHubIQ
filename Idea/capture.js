// Captures real-app screenshots (new design) for the Idea/screenshots set and video frames.
const puppeteer = require("puppeteer");
const path = require("path");
const fs = require("fs");

const APP = process.env.APP_URL || "http://localhost:5283";
const ID = process.env.ANALYSIS_ID;
const USER = "munendra";
const PASS = process.env.GIQ_PASS;
const outDir = path.join(__dirname, "screenshots");
const frameDir = path.join(__dirname, "frames");
for (const d of [outDir, frameDir]) if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--force-color-profile=srgb"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });

  // Log in and store token.
  await page.goto(APP + "/", { waitUntil: "networkidle0" });
  const ok = await page.evaluate(async (u, p) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p }),
    });
    const j = await res.json();
    if (j.token) localStorage.setItem("giq-token", j.token);
    return !!j.token;
  }, USER, PASS);
  console.log("login:", ok);

  const shot = async (file, dir = outDir, fullPage = false) => {
    await page.screenshot({ path: path.join(dir, file), fullPage });
    console.log("✓", file);
  };
  const gotoWait = async (url, ms = 1400) => {
    await page.goto(APP + url, { waitUntil: "networkidle0" });
    await sleep(ms);
  };
  const clickText = (sel, txt) =>
    page.evaluate((s, t) => {
      const el = [...document.querySelectorAll(s)].find((b) => b.textContent.trim().includes(t));
      if (el) el.click();
      return !!el;
    }, sel, txt);

  // 01 — Landing hero
  await gotoWait("/", 1200);
  await shot("01-hero.png");

  // 03 — Questionnaire (with custom instructions field)
  await gotoWait("/tailor?repo=" + encodeURIComponent("https://github.com/fastapi/full-stack-fastapi-template"), 1200);
  await shot("03-questionnaire.png", outDir, true);

  // 04 — My Guide (overview + repo chip)
  await gotoWait("/guide/" + ID, 1600);
  await shot("04-guide.png");

  // 05 — Architecture canvas (with zoom controls)
  await gotoWait("/guide/" + ID + "/architecture", 2000);
  await shot("05-architecture.png");
  // frame: select a node
  await clickText(".arch-node .an-title", "");
  await page.evaluate(() => { const n = document.querySelector(".arch-node"); if (n) n.click(); });
  await sleep(700);
  await shot("v-arch-node.png", frameDir);

  // 06 — Data Flow (vertical left nav)
  await gotoWait("/guide/" + ID + "/dataflow", 1500);
  await shot("06-dataflow.png");
  // frame: middle step selected
  await page.evaluate(() => { const b = document.querySelectorAll(".rail-node-v")[3]; if (b) b.click(); });
  await sleep(700);
  await shot("v-flow-step.png", frameDir);

  // 07 — Schema
  await gotoWait("/guide/" + ID + "/schema", 2000);
  await shot("07-schema.png");

  // frame: a component lesson open in the guide
  await gotoWait("/guide/" + ID, 1400);
  await page.evaluate(() => {
    const items = [...document.querySelectorAll(".item .item-txt")];
    const t = items.find((e) => /Backend|API|Frontend|Database|Service|Core/i.test(e.textContent));
    if (t) t.click();
  });
  await sleep(700);
  await shot("v-guide-component.png", frameDir);

  await browser.close();
  console.log("Done.");
})();
