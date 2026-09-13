// Generates a short cinematic intro clip with Azure OpenAI Sora (sora-2) via the
// OpenAI-compatible /openai/v1/videos preview API. Saves video-work/sora-intro.mp4.
const fs = require("fs");
const path = require("path");

const KEY = process.env.AOAI_KEY;
const BASE = process.env.AOAI_ENDPOINT || "https://gxray-aoai-58781.openai.azure.com";
const DEP = process.env.SORA_DEPLOYMENT || "sora-2";
const V = "api-version=preview";
const outDir = path.join(__dirname, "video-work");
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
const outFile = path.join(outDir, "sora-intro.mp4");
const H = { "api-key": KEY, "Content-Type": "application/json" };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const PROMPT =
  "Cinematic 3D tech title animation on a pure black background. Glowing strands of " +
  "source code, brackets and Git branch lines flow inward through soft volumetric haze " +
  "and weave themselves into a single bright, rounded-square app emblem that pulses with " +
  "light. Warm amber and electric blue accent glow, premium modern Microsoft aesthetic, " +
  "shallow depth of field, slow confident camera push-in, elegant and clean. No text.";

(async () => {
  const create = await fetch(`${BASE}/openai/v1/videos?${V}`, {
    method: "POST", headers: H,
    body: JSON.stringify({ model: DEP, prompt: PROMPT, seconds: "8", size: "1280x720" }),
  });
  if (!create.ok) { console.error("create failed", create.status, await create.text()); process.exit(2); }
  let job = await create.json();
  console.log("video job:", job.id, job.status);

  const jobUrl = `${BASE}/openai/v1/videos/${job.id}?${V}`;
  for (let i = 0; i < 120 && !["completed", "failed", "cancelled"].includes(job.status); i++) {
    await sleep(5000);
    job = await (await fetch(jobUrl, { headers: H })).json();
    process.stdout.write(`\r  ${job.status} ${job.progress || 0}% (${i * 5}s)   `);
  }
  console.log("");
  if (job.status !== "completed") { console.error("job ended:", JSON.stringify(job).slice(0, 500)); process.exit(3); }

  for (const url of [`${BASE}/openai/v1/videos/${job.id}/content?${V}`, `${BASE}/openai/v1/videos/${job.id}/content/video?${V}`]) {
    const vid = await fetch(url, { headers: H });
    if (vid.ok) {
      fs.writeFileSync(outFile, Buffer.from(await vid.arrayBuffer()));
      console.log(`Saved ${outFile} (${(fs.statSync(outFile).size / 1e6).toFixed(2)} MB)`);
      return;
    }
    console.log("download", url.split("?")[0], "->", vid.status);
  }
  process.exit(4);
})();
