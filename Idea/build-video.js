// Builds Idea/walkthrough.mp4: TTS voiceover (deployed Azure Speech) + Ken Burns
// motion over the new-design screenshots, with captions. Uses ffmpeg-static.
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const FF = require("ffmpeg-static");
const API = process.env.API_URL || "http://127.0.0.1:8000";
const USER = "munendra";
const PASS = process.env.GIQ_PASS;
const shots = path.join(__dirname, "screenshots");
const work = path.join(__dirname, "video-work");
if (!fs.existsSync(work)) fs.mkdirSync(work, { recursive: true });
const out = path.join(__dirname, "walkthrough.mp4");
const FONT = "C\\:/Windows/Fonts/segoeuib.ttf";

const scenes = [
  { img: "10-problem-solution.png", cap: "The problem", vo: "Every developer knows the feeling. You join a new project and you're staring at thousands of files, outdated READMEs, and a mental model that lives only in a senior engineer's head. Ramp-up is slow, and every question interrupts a teammate." },
  { img: "00-cover.png", cap: "Meet GitHubIQ", vo: "GitHubIQ turns any Git repository into a living, interactive tutor. Point it at a repo, and six specialist A-I agents read the entire codebase and build an onboarding guide that's tailored to you." },
  { img: "01-hero.png", cap: "Point it at a repo", vo: "It starts with a single URL. Paste any public GitHub repository, and GitHubIQ gets to work. No setup, and nothing leaves your workspace." },
  { img: "03-questionnaire.png", cap: "Tailor your guide", vo: "Tell it who you are. Your role, your experience, and what you want to learn. You can even add custom instructions to steer the analysis toward the parts of the codebase you care about most." },
  { img: "02-analysis.png", cap: "Six agents, in parallel", vo: "Then the crew goes to work. A researcher maps the entry points and hands each specialist its reading list, while the architect, schema, data-flow, tutor and presenter agents run in parallel. Every one an expert in its own domain." },
  { img: "04-guide.png", cap: "Your guided onboarding", vo: "Minutes later you get a guide, not a wall of text. It opens with a plain-language overview. What the project is, what it does, how it works, the key files to read first, and a clear, component-by-component breakdown." },
  { img: "05-architecture.png", cap: "Live architecture map", vo: "Explore the architecture as a living map. Drag the components like a whiteboard, zoom and pan the canvas, go full screen, and tap any node to see its technology and exactly how it connects to the rest of the system." },
  { img: "06-dataflow.png", cap: "Follow a real request", vo: "Follow a real request, end to end. Walk it hop by hop down the left rail, and watch the data transform at every step, with the exact files and code behind each move." },
  { img: "07-schema.png", cap: "Reverse-engineered schema", vo: "The database is reverse-engineered into a draggable diagram. Tables, columns, and the foreign keys that link them. All explained in plain English." },
  { img: "09-system-architecture.png", cap: "Understand any codebase", vo: "That's GitHubIQ. Stop reading stale docs, and start understanding. Point it at your next repository, and build a real mental model in minutes." },
];

async function main() {
  // 1. auth
  const login = await fetch(`${API}/api/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: USER, password: PASS }),
  });
  const { token } = await login.json();
  if (!token) throw new Error("login failed");

  const durationOf = (file) => {
    try { execFileSync(FF, ["-i", file], { stdio: ["ignore", "ignore", "pipe"] }); }
    catch (e) {
      const m = String(e.stderr).match(/Duration:\s*(\d+):(\d+):(\d+\.\d+)/);
      if (m) return (+m[1]) * 3600 + (+m[2]) * 60 + parseFloat(m[3]);
    }
    return 4;
  };
  const sanitize = (s) => s.replace(/[':,]/g, "").replace(/[^\x20-\x7E]/g, "");

  const parts = [];
  for (let i = 0; i < scenes.length; i++) {
    const s = scenes[i];
    const mp3 = path.join(work, `vo_${i}.mp3`);
    // 2. TTS voiceover
    const res = await fetch(`${API}/api/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ text: s.vo }),
    });
    if (!res.ok) throw new Error(`tts ${res.status} for scene ${i}`);
    fs.writeFileSync(mp3, Buffer.from(await res.arrayBuffer()));

    const D = +(durationOf(mp3) + 0.7).toFixed(2);
    const frames = Math.round(D * 30);
    const cap = sanitize(s.cap);
    const img = path.join(shots, s.img);
    const scene = path.join(work, `scene_${i}.mp4`);

    const vf =
      `[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,` +
      `pad=1920:1080:-1:-1:color=0x0A0A0A,setsar=1,` +
      `zoompan=z='min(zoom+0.0004,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=${frames}:s=1920x1080:fps=30,` +
      `drawtext=fontfile='${FONT}':text='${cap}':x=96:y=h-160:fontsize=46:fontcolor=white:` +
      `box=1:boxcolor=0x000000C0:boxborderw=26,` +
      `fade=t=in:st=0:d=0.35,fade=t=out:st=${(D - 0.35).toFixed(2)}:d=0.35,format=yuv420p[v];` +
      `[1:a]afade=t=in:d=0.2,apad,atrim=0:${D},afade=t=out:st=${(D - 0.3).toFixed(2)}:d=0.3[a]`;

    execFileSync(FF, [
      "-y", "-i", img, "-i", mp3,
      "-filter_complex", vf,
      "-map", "[v]", "-map", "[a]", "-t", String(D),
      "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
      "-c:a", "aac", "-b:a", "160k", "-r", "30", scene,
    ], { stdio: ["ignore", "ignore", "inherit"] });
    console.log(`scene ${i} (${D}s): ${s.cap}`);
    parts.push(scene);
  }

  // 3. concat
  const list = path.join(work, "list.txt");
  fs.writeFileSync(list, parts.map((p) => `file '${p.replace(/\\/g, "/")}'`).join("\n"));
  execFileSync(FF, ["-y", "-f", "concat", "-safe", "0", "-i", list, "-c", "copy", out],
    { stdio: ["ignore", "ignore", "inherit"] });
  const mb = (fs.statSync(out).size / 1e6).toFixed(1);
  console.log(`\nDone → ${out} (${mb} MB)`);
}

main().catch((e) => { console.error(e); process.exit(1); });
