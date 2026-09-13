// Records a LIVE demo of the real app: scripted interactions captured via Chrome
// screencast (real motion) with a visible cursor, synced to Azure Speech narration.
// Each scene's audio is padded so audio boundaries match the on-screen holds.
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
const out = path.join(work, "demo.mp4");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const GAP = 0.6; // silence padded after each scene's narration (matches visual hold)

const scenes = [
  { cap: "Onboarding is broken — here's the fix", vo: "Onboarding to a new codebase is painful. Thousands of files, stale docs, and a mental model that lives in someone else's head. GitHubIQ fixes that. Just paste any GitHub repository." },
  { cap: "Tailor the guide to you", vo: "First, tailor the guide to you. Your role, your goals, and even custom instructions that steer the analysis toward exactly what you care about." },
  { cap: "Watch six agents get it done", vo: "Hit generate, and the real work begins. A crew of six specialist agents runs asynchronously. The researcher crawls the repo, finds the entry points, and hands each specialist a focused reading list. Then the architect maps the components, the schema agent reverse-engineers the database, the data-flow agent traces a real request, the tutor explains the language idioms, and the presenter scripts a narrated tour. You watch them work in parallel, progress climbing as each one finishes." },
  { cap: "Your living onboarding guide", vo: "Minutes later, you get a living guide. It opens with a plain-language overview. What the project is, what it does, the key files to read first, and a component-by-component breakdown." },
  { cap: "Live, interactive architecture map", vo: "The architecture is a living map. Zoom, pan, and drag the components like a whiteboard, then click any node to see its technology and how it connects." },
  { cap: "Follow a real request, hop by hop", vo: "Follow a real request end to end. Step down the rail and watch the data transform at every hop, with the exact files and code behind each move." },
  { cap: "Database schema, reverse-engineered", vo: "The database is reverse-engineered into a draggable diagram. Tables, columns, and the foreign keys that link them, all explained in plain English." },
  { cap: "A narrated video tour, with a presenter", vo: "Prefer to watch? Every guide also comes with a narrated video tour, where a presenter walks you through the whole project, scene by scene." },
  { cap: "Export to a polished PDF", vo: "And when you're done, export the entire guide to a polished P D F. Yours to keep, share, or read offline. No lock-in." },
  { cap: "Understand any codebase in minutes", vo: "That's GitHubIQ. Stop reading stale docs. Point it at your next repository, and understand it in minutes." },
];

function durationOf(file) {
  try { execFileSync(FF, ["-i", file], { stdio: ["ignore", "ignore", "pipe"] }); }
  catch (e) { const m = String(e.stderr).match(/Duration:\s*(\d+):(\d+):(\d+\.\d+)/); if (m) return (+m[1]) * 3600 + (+m[2]) * 60 + parseFloat(m[3]); }
  return 6;
}

async function main() {
  const login = await fetch(`${API}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: USER, password: PASS }) });
  const { token } = await login.json();
  const runRes = await fetch(`${API}/api/analyze`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ repo_url: "https://github.com/django/django", preferences: { role: "backend", familiarity: "comfortable", goals: ["Architecture & components"], depth: "guided" } }) });
  const throwId = (await runRes.json()).id;

  // Narration: per scene, padded with GAP seconds of silence so boundaries match visuals.
  const listLines = [];
  const dur = [];
  for (let i = 0; i < scenes.length; i++) {
    const raw = path.join(work, `vo_${i}.mp3`);
    const pad = path.join(work, `vo_${i}_p.mp3`);
    const res = await fetch(`${API}/api/tts`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ text: scenes[i].vo }) });
    fs.writeFileSync(raw, Buffer.from(await res.arrayBuffer()));
    execFileSync(FF, ["-y", "-i", raw, "-af", `apad=pad_dur=${GAP}`, "-c:a", "libmp3lame", "-q:a", "4", pad], { stdio: "ignore" });
    dur.push(durationOf(pad));
    listLines.push(`file '${pad.replace(/\\/g, "/")}'`);
  }
  const alist = path.join(work, "audio.txt");
  fs.writeFileSync(alist, listLines.join("\n"));
  const narration = path.join(work, "narration.mp3");
  execFileSync(FF, ["-y", "-f", "concat", "-safe", "0", "-i", alist, "-c", "copy", narration], { stdio: "ignore" });
  const cum = [];
  dur.reduce((a, d, i) => (cum[i] = a + d), 0);
  console.log("scene durations:", dur.map((d) => d.toFixed(1)).join(", "));

  const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox", "--force-color-profile=srgb", "--window-size=1600,900"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  await page.goto(APP + "/", { waitUntil: "networkidle0" });
  await page.evaluate(async (u, p) => { const r = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) }); localStorage.setItem("giq-token", (await r.json()).token); }, USER, PASS);

  const client = await page.createCDPSession();
  let nFrame = 0, firstTs = null, resolveFirst;
  const firstFrame = new Promise((r) => (resolveFirst = r));
  const frames = [];
  client.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
    try { await client.send("Page.screencastFrameAck", { sessionId }); } catch {}
    if (firstTs === null) { firstTs = metadata.timestamp; resolveFirst(); }
    const file = path.join(framesDir, `f_${String(++nFrame).padStart(6, "0")}.jpg`);
    fs.writeFileSync(file, Buffer.from(data, "base64"));
    frames.push({ file, t: metadata.timestamp - firstTs });
  });
  const startCast = async () => { try { await client.send("Page.startScreencast", { format: "jpeg", quality: 80, maxWidth: 1600, maxHeight: 900, everyNthFrame: 1 }); } catch {} };

  // Inject caption bar + animated cursor + click ripple into the page.
  const ensureUI = () => page.evaluate(() => {
    if (window.__uiReady) return;
    const st = document.createElement("style");
    st.textContent = `#__demo_cap{position:fixed;left:0;right:0;bottom:0;z-index:99998;padding:22px 34px;font:700 26px 'Segoe UI',sans-serif;color:#fff;background:linear-gradient(0deg,rgba(0,0,0,.82),transparent);pointer-events:none;letter-spacing:-.2px;text-shadow:0 2px 12px rgba(0,0,0,.6)}
    #__cur{position:fixed;z-index:100000;left:0;top:0;width:26px;height:26px;margin:-3px 0 0 -3px;pointer-events:none;transition:transform .45s cubic-bezier(.22,.61,.36,1);filter:drop-shadow(0 2px 4px rgba(0,0,0,.55))}
    .__ripple{position:fixed;z-index:99999;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;background:rgba(255,185,0,.5);pointer-events:none;animation:__rip .55s ease-out forwards}
    @keyframes __rip{from{transform:scale(1);opacity:.85}to{transform:scale(4.2);opacity:0}}`;
    document.head.appendChild(st);
    const cap = document.createElement("div"); cap.id = "__demo_cap"; document.body.appendChild(cap);
    const c = document.createElement("div"); c.id = "__cur";
    c.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M5 2.5l14.5 8.2-6.2 1.5-3.4 6.4z" fill="#fff" stroke="#111" stroke-width="1.3" stroke-linejoin="round"/></svg>';
    c.style.transform = "translate(780px,430px)"; document.body.appendChild(c);
    window.__cur = (x, y) => { c.style.transition = "transform .45s cubic-bezier(.22,.61,.36,1)"; c.style.transform = `translate(${x}px,${y}px)`; };
    window.__curFast = (x, y) => { c.style.transition = "none"; c.style.transform = `translate(${x}px,${y}px)`; };
    window.__flash = (x, y) => { const r = document.createElement("div"); r.className = "__ripple"; r.style.left = x + "px"; r.style.top = y + "px"; document.body.appendChild(r); setTimeout(() => r.remove(), 620); };
    window.__setcap = (t) => { document.getElementById("__demo_cap").textContent = t; };
    window.__uiReady = true;
  });
  const setCap = (t) => page.evaluate((x) => window.__setcap && window.__setcap(x), t);
  const moveTo = async (x, y, hold = 520) => { await page.evaluate((a, b) => window.__cur && window.__cur(a, b), x, y); await sleep(hold); };
  const flash = (x, y) => page.evaluate((a, b) => window.__flash && window.__flash(a, b), x, y);
  const rectOf = async (sel) => { const el = await page.$(sel); if (!el) return null; const b = await el.boundingBox(); return b ? { x: b.x + b.width / 2, y: b.y + b.height / 2 } : null; };
  const clickByText = async (sel, txt, hold = 500) => {
    const r = await page.evaluate((s, t) => { const el = [...document.querySelectorAll(s)].find((b) => b.textContent.trim() === t || b.textContent.includes(t)); if (!el) return null; const q = el.getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2 }; }, sel, txt);
    if (!r) return false;
    await moveTo(r.x, r.y); await flash(r.x, r.y);
    await page.evaluate((s, t) => { const el = [...document.querySelectorAll(s)].find((b) => b.textContent.trim() === t || b.textContent.includes(t)); if (el) el.click(); }, sel, txt);
    await sleep(hold); return true;
  };
  const clickSel = async (sel, hold = 500) => { const r = await rectOf(sel); if (!r) return false; await moveTo(r.x, r.y); await flash(r.x, r.y); await page.evaluate((s) => document.querySelector(s)?.click(), sel); await sleep(hold); return true; };
  const typeInto = async (sel, text) => { const r = await rectOf(sel); if (r) { await moveTo(r.x, r.y, 400); await flash(r.x, r.y); } await page.focus(sel); await page.type(sel, text, { delay: 26 }); };
  const dragNode = async (sel, dx, dy) => {
    const el = await page.$(sel); if (!el) return; const b = await el.boundingBox(); if (!b) return;
    const x = b.x + b.width / 2, y = b.y + b.height / 2;
    await moveTo(x, y, 420); await page.mouse.move(x, y); await page.mouse.down();
    const steps = 24;
    for (let k = 1; k <= steps; k++) { const nx = x + dx * k / steps, ny = y + dy * k / steps; await page.mouse.move(nx, ny); if (k % 3 === 0) await page.evaluate((a, b2) => window.__curFast && window.__curFast(a, b2), nx, ny); }
    await page.mouse.up(); await sleep(350);
  };
  const gotoWait = async (url, ms = 1200) => { await page.goto(APP + url, { waitUntil: "networkidle0" }); await startCast(); await ensureUI(); await sleep(ms); };

  await startCast();
  await ensureUI();
  await firstFrame;
  const t0 = Date.now();
  const waitScene = async (i) => { const r = t0 + cum[i] * 1000 - Date.now(); if (r > 0) await sleep(r); };

  // 1 — landing + type repo URL
  await setCap(scenes[0].cap);
  await page.evaluate(() => window.scrollTo({ top: 0 }));
  await sleep(700);
  await typeInto(".repo-input input", REPO);
  await waitScene(0);

  // 2 — questionnaire
  await gotoWait("/tailor?repo=" + encodeURIComponent(REPO), 900);
  await setCap(scenes[1].cap);
  await clickByText(".grid-3 .card h4", "Backend", 650);
  await clickByText(".chip", "Database schema", 550);
  await typeInto(".custom-instructions", "Focus on how the FastAPI backend, the SQLModel database and the React frontend connect.");
  await waitScene(1);

  // 3 — live multi-agent working demonstration
  await gotoWait("/analysis/" + throwId, 1200);
  await setCap(scenes[2].cap);
  const rows = await page.$$eval(".agent-row", (els) => els.map((e) => { const r = e.getBoundingClientRect(); return { x: r.x + 42, y: r.y + r.height / 2 }; }));
  for (const r of rows) { await moveTo(r.x, r.y, 320); await flash(r.x, r.y); await sleep(2500); }
  await waitScene(2);

  // 4 — guide overview
  await gotoWait("/guide/" + MAIN, 1300);
  await setCap(scenes[3].cap);
  await sleep(500);
  await page.evaluate(() => window.scrollBy({ top: 320, behavior: "smooth" }));
  await sleep(1100);
  await clickByText(".item .item-txt", "Backend", 700).catch(() => {});
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await waitScene(3);

  // 5 — architecture
  await clickByText(".tab-bar .chip", "Architecture", 1400);
  await setCap(scenes[4].cap);
  await clickByText(".canvas-tools button", "+", 550);
  await clickByText(".canvas-tools button", "+", 550);
  await dragNode(".arch-node", 150, 90);
  await clickByText(".canvas-tools button", "View", 450);
  await page.evaluate(() => { const n2 = document.querySelectorAll(".arch-node")[1]; if (n2) n2.click(); });
  await sleep(400);
  await waitScene(4);

  // 6 — data flow
  await clickByText(".tab-bar .chip", "Data Flow", 1200);
  await setCap(scenes[5].cap);
  for (const idx of [1, 2, 3, 4]) { await clickByText(".rail-node-v .rail-actor", null, 0).catch(() => {}); await page.evaluate((i) => { const b = document.querySelectorAll(".rail-node-v")[i]; if (b) { const q = b.getBoundingClientRect(); window.__cur && window.__cur(q.x + 30, q.y + q.height / 2); window.__flash && window.__flash(q.x + 30, q.y + q.height / 2); b.click(); } }, idx); await sleep(1100); }
  await waitScene(5);

  // 7 — schema
  await clickByText(".tab-bar .chip", "Schema", 1400);
  await setCap(scenes[6].cap);
  await dragNode(".er-table", 170, 70);
  await dragNode(".er-table", -120, 40);
  await waitScene(6);

  // 8 — narrated video tour
  await clickByText(".tab-bar .chip", "Video", 1600);
  await setCap(scenes[7].cap);
  await clickByText(".video-controls button", "Play", 800);
  await sleep(1200);
  await waitScene(7);

  // 9 — export to PDF
  await clickByText(".tab-bar .chip", "My Guide", 1100);
  await setCap(scenes[8].cap);
  await sleep(500);
  await clickByText(".topbar .btn", "Export", 900);
  await waitScene(8);

  // 10 — close
  await setCap(scenes[9].cap);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await waitScene(9);

  try { await client.send("Page.stopScreencast"); } catch {}
  await sleep(300);
  await browser.close();
  console.log("frames:", frames.length, "span:", (frames[frames.length - 1]?.t || 0).toFixed(1), "s  audio:", cum[cum.length - 1].toFixed(1), "s");

  // Assemble variable-duration frames → 30fps, mux narration.
  const total = cum[cum.length - 1];
  const ff = ["ffconcat version 1.0"];
  for (let i = 0; i < frames.length; i++) {
    const next = i + 1 < frames.length ? frames[i + 1].t : total;
    ff.push(`file '${frames[i].file.replace(/\\/g, "/")}'`, `duration ${Math.max(0.016, next - frames[i].t).toFixed(3)}`);
  }
  ff.push(`file '${frames[frames.length - 1].file.replace(/\\/g, "/")}'`);
  const framesTxt = path.join(work, "frames.txt");
  fs.writeFileSync(framesTxt, ff.join("\n"));
  execFileSync(FF, ["-y", "-f", "concat", "-safe", "0", "-i", framesTxt, "-i", narration,
    "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:-1:-1:color=0x0A0A0A,fps=30,format=yuv420p",
    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-shortest", out],
    { stdio: ["ignore", "ignore", "inherit"] });
  console.log(`\nDemo → ${out} (${(fs.statSync(out).size / 1e6).toFixed(1)} MB)`);
}

main().catch((e) => { console.error(e); process.exit(1); });
