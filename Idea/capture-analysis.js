// Starts an analysis and captures the live progress screen (02-analysis.png).
const puppeteer = require("puppeteer");
const path = require("path");

const APP = process.env.APP_URL || "http://localhost:5283";
const USER = "munendra";
const PASS = process.env.GIQ_PASS;
const outDir = path.join(__dirname, "screenshots");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox", "--force-color-profile=srgb"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
  await page.goto(APP + "/", { waitUntil: "networkidle0" });

  const id = await page.evaluate(async (u, p) => {
    const login = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) });
    const j = await login.json();
    localStorage.setItem("giq-token", j.token);
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + j.token },
      body: JSON.stringify({ repo_url: "https://github.com/pallets/flask", preferences: { role: "backend", familiarity: "comfortable", goals: ["Architecture & components"], depth: "guided", custom_instructions: "" } }),
    });
    const a = await res.json();
    return a.id;
  }, USER, PASS);
  console.log("analysis id:", id);

  // Capture while agents are running.
  await sleep(9000);
  await page.goto(APP + "/analysis/" + id, { waitUntil: "networkidle0" });
  await sleep(1500);
  await page.screenshot({ path: path.join(outDir, "02-analysis.png") });
  console.log("✓ 02-analysis.png");
  await browser.close();
})();
