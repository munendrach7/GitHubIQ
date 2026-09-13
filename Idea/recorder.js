// Records a LIVE demo of the real app: scripted interactions captured via Chrome
// screencast (real motion), synced to Azure Speech narration. Outputs walkthrough.mp4.
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer");
const FF = require("ffmpeg-static");

const APP = process.env.APP_URL || "http://localhost:5283";
const API = process.env.API_URL || "http://127.0.0.1:8000";
const USER = "munendra";
const PASS = process.env.GIQ_PASS;
const MAIN = process.env.ANALYSIS_ID;
const REPO = "https://github.com/fastapi/full-stack-fastapi-template";

const work = path.join(__dirname, "video-work");
const framesDir = path.join(work, "frames");
fs.rmSync(work, { recursive: true, force: true });
fs.mkdirSync(framesDir, { recursive: true });
const out = path.join(__dirname, "walkthrough.mp4");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const scenes = [
  { cap: "Onboarding is broken — here's the fix", vo: "Onboarding to a new codebase is painful. Thousands of files, stale docs, and a mental model that lives in someone else's head. GitHubIQ fixes that. Just paste any GitHub repository." },
  { cap: "Tailor the guide to you", vo: "First, tailor the guide to you. Your role, your goals, and even custom instructions that steer the analysis toward exactly what you care about." },
  { cap: "Six specialist agents, in parallel", vo: "Hit generate, and six specialist agents go to work in parallel. A researcher maps the code and hands each specialist its reading list — the architect, schema, data-flow, tutor and presenter agents." },
  { cap: "Your living onboarding guide", vo: "Minutes later, you get a living guide. It opens with a plain-language overview. What the project is, what it does, the key files to read first, and a component-by-component breakdown." },
  { cap: "Live, interactive architecture map", vo: "The architecture is a living map. Zoom, pan, and drag the components like a whiteboard, then click any node to see its technology and how it connects to the rest of the system." },
  { cap: "Follow a real request, hop by hop", vo: "Follow a real request end to end. Step down the rail and watch the data transform at every hop, with the exact files and code behind each move." },
  { cap: "Database schema, reverse-engineered", vo: "The database is reverse-engineered into a draggable diagram. Tables, columns, and the foreign keys that link them, all explained in plain English." },
  { cap: "Understand any codebase in minutes", vo: "That's GitHubIQ. Stop reading stale docs. Point it at your next repository, and understand it in minutes." },
];

function durationOf(file) {
  try { execFileSync(FF, ["-i", file], { stdio: ["ignore", "ignore", "pipe"] }); }
  catch (e) {
    const m = String(e.stderr).match(/Duration:\s*(\d+):(\d+):(\d+\.\d+)/);
    if (m) return (+m[1]) * 3600 + (+m[2]) * 60 + parseFloat(m[3]);
  }
  return 6;
}

async function main() {
  // 1. token + a throwaway running analysis for the live progress scene.
  const login = await fetch(`${API}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: USER, password: PASS }) });
  const { token } = await login.json();
  const runRes = await fetch(`${API}/api/analyze`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ repo_url: "https://github.com/pallets/flask", preferences: { role: "backend", familiarity: "comfortable", goals: ["Architecture & components"], depth: "guided" } }) });
  const throwId = (await runRes.json()).id;

  // 2. narration per scene + durations + concatenated track.
  const listLines = [];
  const dur = [];
  for (let i = 0; i < scenes.length; i++) {
    const mp3 = path.join(work, `vo_${i}.mp3`);
    const res = await fetch(`${API}/api/tts`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ text: scenes[i].vo }) });
    fs.writeFileSync(mp3, Buffer.from(await res.arrayBuffer()));
    dur.push(durationOf(mp3) + 0.5); // small tail per scene
    listLines.push(`file '${mp3.replace(/\\/g, "/")}'`);
  }
  const alist = path.join(work, "audio.txt");
  fs.writeFileSync(alist, listLines.join("\n"));
  const narration = path.join(work, "narration.mp3");
  execFileSync(FF, ["-y", "-f", "concat", "-safe", "0", "-i", alist, "-c", "copy", narration], { stdio: "ignore" });
  const cum = [];
  dur.reduce((a, d, i) => (cum[i] = a + d), 0);
  console.log("scene durations:", dur.map((d) => d.toFixed(1)).join(", "));

  // 3. browser + screencast.
  const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox", "--force-color-profile=srgb", "--window-size=1600,900"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  await page.goto(APP + "/", { waitUntil: "networkidle0" });
  await page.evaluate(async (u, p) => {
    const r = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) });
    localStorage.setItem("giq-token", (await r.json()).token);
  }, USER, PASS);

  const client = await page.createCDPSession();
  let n = 0;
  const frames = [];
  let firstTs = null;
  client.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
    try { await client.send("Page.screencastFrameAck", { sessionId }); } catch {}
    if (firstTs === null) firstTs = metadata.timestamp;
    const file = path.join(framesDir, `f_${String(++n).padStart(6, "0")}.jpg`);
    fs.writeFileSync(file, Buffer.from(data, "base64"));
    frames.push({ file, t: metadata.timestamp - firstTs });
  });
  const startCast = async () => { try { await client.send("Page.startScreencast", { format: "jpeg", quality: 80, maxWidth: 1600, maxHeight: 900, everyNthFrame: 1 }); } catch {} };

  // Caption overlay helpers (injected into the page).
  const ensureCaption = (text) =>
    page.evaluate((t) => {
      let el = document.getElementById("__demo_cap");
      if (!el) {
        el = document.createElement("div");
        el.id = "__demo_cap";
        el.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:99999;padding:22px 34px;font:700 26px 'Segoe UI',sans-serif;color:#fff;background:linear-gradient(0deg,rgba(0,0,0,0.82),transparent);pointer-events:none;letter-spacing:-0.2px;text-shadow:0 2px 12px rgba(0,0,0,0.6)";
        document.body.appendChild(el);
      }
      el.textContent = t;
    }, text);

  const clickText = (sel, txt) => page.evaluate((s, t) => { const el = [...document.querySelectorAll(s)].find((b) => b.textContent.trim() === t || b.textContent.trim().includes(t)); if (el) el.click(); return !!el; }, sel, txt);
  const gotoWait = async (url, ms = 1200) => { await page.goto(APP + url, { waitUntil: "networkidle0" }); await startCast(); await sleep(ms); };
  const dragNode = async (sel, dx, dy) => {
    const el = await page.$(sel);
    if (!el) return;
    const b = await el.boundingBox();
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
    await page.mouse.down();
    await page.mouse.move(b.x + b.width / 2 + dx, b.y + b.height / 2 + dy, { steps: 26 });
    await page.mouse.up();
  };

  await startCast();
  const t0 = Date.now();
  const waitScene = async (i) => { const r = t0 + cum[i] * 1000 - Date.now(); if (r > 0) await sleep(r); };

  // ---- Scene 1: landing + type repo URL ----
  await ensureCaption(scenes[0].cap);
  await sleep(700);
  await page.evaluate(() => window.scrollTo({ top: 0 }));
  const input = await page.$(".repo-input input");
  if (input) { await input.click(); await page.type(".repo-input input", REPO, { delay: 42 }); }
  await waitScene(0);

  // ---- Scene 2: questionnaire ----
  await gotoWait("/tailor?repo=" + encodeURIComponent(REPO), 900);
  await ensureCaption(scenes[1].cap);
  await sleep(500);
  await clickText(".grid-3 .card h4", "Backend");
  await sleep(500);
  await clickText(".chip", "Database schema");
  await sleep(400);
  const ta = await page.$(".custom-instructions");
  if (ta) { await ta.click(); await page.type(".custom-instructions", "Focus on how the FastAPI backend, the SQLModel database and the React frontend connect.", { delay: 24 }); }
  await waitScene(1);

  // ---- Scene 3: live analysis progress ----
  await gotoWait("/analysis/" + throwId, 1000);
  await ensureCaption(scenes[2].cap);
  await waitScene(2);

  // ---- Scene 4: guide overview ----
  await gotoWait("/guide/" + MAIN, 1300);
  await ensureCaption(scenes[3].cap);
  await sleep(700);
  await page.evaluate(() => window.scrollBy({ top: 320, behavior: "smooth" }));
  await sleep(1200);
  await page.evaluate(() => { const it = [...document.querySelectorAll(".item .item-txt")].find((e) => /Backend|API|Database|Frontend|Service|Core/i.test(e.textContent)); if (it) it.click(); });
  await sleep(900);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await waitScene(3);

  // ---- Scene 5: architecture (zoom + drag + select) ----
  await clickText(".tab-bar .chip", "Architecture");
  await sleep(1400);
  await ensureCaption(scenes[4].cap);
  for (let k = 0; k < 3; k++) { await page.evaluate(() => { const b = [...document.querySelectorAll(".canvas-tools button")].find((x) => x.textContent.trim() === "+"); if (b) b.click(); }); await sleep(450); }
  await dragNode(".arch-node", 150, 90);
  await sleep(500);
  await page.evaluate(() => { const b = [...document.querySelectorAll(".canvas-tools button")].find((x) => x.textContent.includes("View")); if (b) b.click(); });
  await sleep(400);
  await page.evaluate(() => { const n2 = document.querySelectorAll(".arch-node")[1]; if (n2) n2.click(); });
  await waitScene(4);

  // ---- Scene 6: data flow (step through) ----
  await clickText(".tab-bar .chip", "Data Flow");
  await sleep(1200);
  await ensureCaption(scenes[5].cap);
  for (const idx of [1, 2, 3, 4]) { await page.evaluate((i) => { const b = document.querySelectorAll(".rail-node-v")[i]; if (b) b.click(); }, idx); await sleep(1100); }
  await waitScene(5);

  // ---- Scene 7: schema (drag a table) ----
  await clickText(".tab-bar .chip", "Schema");
  await sleep(1400);
  await ensureCaption(scenes[6].cap);
  await dragNode(".er-table", 170, 70);
  await sleep(600);
  await dragNode(".er-table", -120, 40);
  await waitScene(6);

  // ---- Scene 8: close ----
  await clickText(".tab-bar .chip", "My Guide");
  await sleep(900);
  await ensureCaption(scenes[7].cap);
  await waitScene(7);

  try { await client.send("Page.stopScreencast"); } catch {}
  await sleep(300);
  await browser.close();
  console.log("captured frames:", frames.length, "over", (frames[frames.length - 1]?.t || 0).toFixed(1), "s");

  // 4. assemble: variable-duration frames → 30fps video, mux narration.
  const total = cum[cum.length - 1];
  const ff = ["ffconcat version 1.0"];
  for (let i = 0; i < frames.length; i++) {
    const next = i + 1 < frames.length ? frames[i + 1].t : total;
    const d = Math.max(0.016, next - frames[i].t);
    ff.push(`file '${frames[i].file.replace(/\\/g, "/")}'`, `duration ${d.toFixed(3)}`);
  }
  ff.push(`file '${frames[frames.length - 1].file.replace(/\\/g, "/")}'`);
  const framesTxt = path.join(work, "frames.txt");
  fs.writeFileSync(framesTxt, ff.join("\n"));

  execFileSync(FF, [
    "-y", "-f", "concat", "-safe", "0", "-i", framesTxt, "-i", narration,
    "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:-1:-1:color=0x0A0A0A,fps=30,format=yuv420p",
    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-shortest", out,
  ], { stdio: ["ignore", "ignore", "inherit"] });
  console.log(`\nDone → ${out} (${(fs.statSync(out).size / 1e6).toFixed(1)} MB)`);
}

main().catch((e) => { console.error(e); process.exit(1); });
