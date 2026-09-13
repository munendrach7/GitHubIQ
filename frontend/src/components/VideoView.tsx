import { useEffect, useMemo, useRef, useState } from "react";
import type { AnalysisResult, VideoScene } from "../types";
import { fetchNarration, ttsAvailable } from "../api";

const ACCENT: Record<string, string> = {
  blue: "var(--blue)", purple: "var(--purple)", green: "var(--green)",
  orange: "var(--orange)", pink: "var(--pink)",
};

/** A friendly male presenter, drawn inline so it always renders. */
function Presenter({ speaking }: { speaking: boolean }) {
  return (
    <svg className={`presenter ${speaking ? "speaking" : ""}`} viewBox="0 0 120 130" width="96" height="104">
      <defs>
        <linearGradient id="pg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1f6feb" /><stop offset="1" stopColor="#6f42c1" />
        </linearGradient>
      </defs>
      <circle cx="60" cy="58" r="52" fill="url(#pg)" opacity="0.16" />
      {/* shoulders */}
      <path d="M18 128 C22 96 44 86 60 86 C76 86 98 96 102 128 Z" fill="#30507a" />
      <path d="M52 84 h16 v10 a8 8 0 0 1 -16 0 Z" fill="#e9b48f" />
      {/* head */}
      <circle cx="60" cy="52" r="26" fill="#f0c19a" />
      {/* hair */}
      <path d="M35 46 C34 26 52 20 60 20 C70 20 87 27 85 47 C80 38 70 34 60 34 C50 34 40 38 35 46 Z" fill="#3a2c22" />
      {/* eyes */}
      <circle cx="51" cy="50" r="2.6" fill="#2b2b2b" />
      <circle cx="69" cy="50" r="2.6" fill="#2b2b2b" />
      {/* brows */}
      <path d="M46 44 q5 -3 10 0" stroke="#3a2c22" strokeWidth="2" fill="none" strokeLinecap="round" />
      <path d="M64 44 q5 -3 10 0" stroke="#3a2c22" strokeWidth="2" fill="none" strokeLinecap="round" />
      {/* mouth (animates when speaking) */}
      <g className="mouth">
        <ellipse cx="60" cy="64" rx="7" ry="3.2" fill="#7a3b34" />
      </g>
    </svg>
  );
}

function VisualStage({ scene, result }: { scene: VideoScene; result: AnalysisResult }) {
  const accent = ACCENT[scene.accent] || "var(--blue)";
  if (scene.visual === "components") {
    return (
      <div className="vstage">
        <div className="v-chips">
          {result.research.components.map((c, i) => (
            <div key={c.id} className="v-chip pop" style={{ animationDelay: `${i * 0.15}s`, borderColor: accent }}>
              <b>🧩 {c.name}</b><span className="dim">{c.kind}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (scene.visual === "architecture") {
    const nodes = result.architecture.nodes.slice(0, 6);
    return (
      <div className="vstage">
        <div className="v-arch">
          {nodes.map((n, i) => (
            <div key={n.id} className="v-node pop" style={{ animationDelay: `${i * 0.12}s`, borderColor: accent }}>
              <span className="v-node-dot" style={{ background: accent }} />{n.label}
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (scene.visual === "dataflow") {
    const steps = result.dataflow.steps.slice(0, 6);
    return (
      <div className="vstage">
        <div className="v-flow">
          {steps.map((s, i) => (
            <div key={s.index} className="v-flow-item pop" style={{ animationDelay: `${i * 0.18}s` }}>
              <span className="v-flow-num" style={{ background: accent }}>{s.index}</span>
              <span>{s.actor}</span>
              {i < steps.length - 1 && <span className="v-flow-arrow">→</span>}
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (scene.visual === "schema") {
    return (
      <div className="vstage">
        <div className="v-tables">
          {result.schema.tables.map((t, i) => (
            <div key={t.name} className="v-table pop" style={{ animationDelay: `${i * 0.14}s` }}>
              <div className="v-table-h" style={{ background: `color-mix(in srgb, ${accent} 20%, transparent)` }}>🗄️ {t.name}</div>
              {t.columns.slice(0, 4).map((c) => <div key={c.name} className="v-table-c">{c.name}</div>)}
            </div>
          ))}
        </div>
      </div>
    );
  }
  // intro / outro / tech
  return (
    <div className="vstage v-intro">
      <div className="v-badge pop" style={{ background: `color-mix(in srgb, ${accent} 18%, transparent)`, color: accent }}>
        {scene.visual === "outro" ? "🎓 You're ready" : `${result.repo.owner}/${result.repo.name}`}
      </div>
      <div className="v-title pop" style={{ animationDelay: "0.1s" }}>{scene.title}</div>
      {result.video.tagline && scene.visual === "intro" && (
        <div className="v-tagline pop" style={{ animationDelay: "0.25s" }}>{result.video.tagline}</div>
      )}
    </div>
  );
}

export default function VideoView({ result }: { result: AnalysisResult }) {
  const scenes = result.video?.scenes || [];
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [hasTts, setHasTts] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const cache = useRef<Map<number, string>>(new Map());
  const timer = useRef<number>();

  const scene = scenes[Math.min(idx, scenes.length - 1)];

  useEffect(() => {
    ttsAvailable().then(setHasTts);
    return () => {
      window.clearTimeout(timer.current);
      audioRef.current?.pause();
      cache.current.forEach((u) => URL.revokeObjectURL(u));
    };
  }, []);

  const stopAudio = () => {
    window.clearTimeout(timer.current);
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
    }
  };

  const advance = () => {
    setIdx((i) => (i + 1 < scenes.length ? i + 1 : i));
    setPlaying((p) => (idx + 1 < scenes.length ? p : false));
  };

  // Drive playback whenever scene or play state changes.
  useEffect(() => {
    stopAudio();
    if (!playing || !scene) return;
    let cancelled = false;

    const timed = () => {
      const words = scene.narration.split(/\s+/).length;
      const secs = Math.min(15, Math.max(5, words / 2.6));
      timer.current = window.setTimeout(() => !cancelled && advance(), secs * 1000);
    };

    const playAudio = async () => {
      if (hasTts === false || muted) return timed();
      setLoading(true);
      try {
        let url = cache.current.get(idx);
        if (!url) {
          url = await fetchNarration(scene.narration);
          cache.current.set(idx, url);
        }
        if (cancelled) return;
        const audio = new Audio(url);
        audioRef.current = audio;
        audio.muted = muted;
        audio.onended = () => !cancelled && advance();
        audio.onerror = () => !cancelled && timed();
        await audio.play().catch(() => timed());
      } catch {
        if (!cancelled) timed();
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    playAudio();

    return () => {
      cancelled = true;
      stopAudio();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, playing, hasTts, muted]);

  const wordCount = useMemo(
    () => scenes.reduce((a, s) => a + s.narration.split(/\s+/).length, 0),
    [scenes]
  );

  if (!scenes.length) {
    return <div className="glass empty">No video explainer was generated for this repository.</div>;
  }

  const accent = ACCENT[scene.accent] || "var(--blue)";

  return (
    <div>
      <div className="page-head" style={{ paddingTop: 0 }}>
        <h2 style={{ fontSize: 24 }}>
          🎥 {result.video.title || "Project explainer"}
          {hasTts && <span className="tag green" style={{ marginLeft: 10 }}>narrated</span>}
        </h2>
        <p>A quick overview presented by {result.video.persona}. ~{Math.round(wordCount / 2.6)}s · {scenes.length} scenes.</p>
      </div>

      <div className="video-frame glass" style={{ ["--accent" as string]: accent }}>
        <div className="video-stage">
          <VisualStage scene={scene} result={result} />

          <div className="video-bullets">
            {scene.bullets.map((b, i) => (
              <div key={i} className="video-bullet pop" style={{ animationDelay: `${0.2 + i * 0.18}s` }}>
                <span className="vb-dot" style={{ background: accent }} /> {b}
              </div>
            ))}
          </div>

          <div className="presenter-wrap">
            <Presenter speaking={playing && !loading} />
            <div className="presenter-name">{result.video.persona}</div>
          </div>

          <div className="video-caption">{scene.narration}</div>
        </div>

        <div className="video-controls">
          <button className="icon-btn" onClick={() => { setIdx(Math.max(0, idx - 1)); }} title="Previous scene">⏮</button>
          <button className="btn accent" onClick={() => setPlaying((p) => !p)} style={{ minWidth: 110, justifyContent: "center" }}>
            {loading ? <span className="spinner" /> : playing ? "⏸ Pause" : "▶ Play"}
          </button>
          <button className="icon-btn" onClick={() => { if (idx + 1 < scenes.length) setIdx(idx + 1); }} title="Next scene">⏭</button>
          <button className="icon-btn" onClick={() => setMuted((m) => !m)} title="Mute">{muted ? "🔇" : "🔊"}</button>
          <div className="video-progress">
            {scenes.map((s, i) => (
              <button
                key={s.id}
                className={`vp-dot ${i === idx ? "on" : ""} ${i < idx ? "done" : ""}`}
                onClick={() => setIdx(i)}
                title={s.title}
              />
            ))}
          </div>
          <span className="dim" style={{ fontSize: 12.5 }}>{idx + 1} / {scenes.length}</span>
        </div>
      </div>

      {hasTts === false && (
        <p className="dim" style={{ fontSize: 12.5, marginTop: 10 }}>
          🔈 Voice narration isn't configured on this server — captions advance automatically instead.
        </p>
      )}
    </div>
  );
}
