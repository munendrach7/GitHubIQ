import { useState } from "react";
import type { AnalysisResult, Lesson } from "../types";
import Markdown from "./Markdown";

export default function GuideView({ result }: { result: AnalysisResult }) {
  const lessons = result.guide.lessons;
  const [activeId, setActiveId] = useState(lessons[0]?.id);
  const active: Lesson | undefined = lessons.find((l) => l.id === activeId) || lessons[0];

  const sections = lessons.reduce<Record<string, Lesson[]>>((acc, l) => {
    (acc[l.section] ||= []).push(l);
    return acc;
  }, {});

  const idx = lessons.findIndex((l) => l.id === active?.id);
  const progressPct = lessons.length ? Math.round(((idx + 1) / lessons.length) * 100) : 0;

  return (
    <div className="guide-layout">
      <div className="glass side">
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
          <span className="muted">Your onboarding</span>
          <b>{progressPct}%</b>
        </div>
        <div className="bar" style={{ margin: "8px 0 4px" }}><i style={{ width: `${progressPct}%` }} /></div>
        <div className="muted" style={{ fontSize: 12 }}>
          {idx + 1} of {lessons.length} lessons
        </div>

        {Object.entries(sections).map(([sect, items]) => (
          <div key={sect}>
            <div className="sect">{sect.toUpperCase()}</div>
            {items.map((l) => (
              <div
                key={l.id}
                className={`item ${l.id === active?.id ? "active" : ""}`}
                onClick={() => setActiveId(l.id)}
              >
                <span className="item-ic">{l.icon || (l.id === active?.id ? "▶" : "○")}</span>
                <span className="item-txt">{l.title}</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="guide-main">
        <div className="muted" style={{ fontSize: 13 }}>
          {active?.section} / <b style={{ color: "var(--text)" }}>{active?.title}</b>
        </div>
        <div className="page-head" style={{ paddingTop: 8 }}>
          <h2 style={{ fontSize: 28 }}>{active?.icon} {active?.title}</h2>
          <p>{active?.summary}</p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="tag blue">Lesson {idx + 1} of {lessons.length}</span>
          {active?.component && <span className="tag orange">{active.component}</span>}
          {active?.tags.map((t) => (
            <span key={t} className="tag purple">{t}</span>
          ))}
        </div>
        <div className="glass card lesson-body">
          <Markdown text={active?.body || active?.summary || ""} />
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 20, gap: 10 }}>
          <button
            className="btn ghost"
            disabled={idx <= 0}
            onClick={() => setActiveId(lessons[idx - 1]?.id)}
          >
            ← Previous
          </button>
          <button
            className="btn accent"
            disabled={idx >= lessons.length - 1}
            onClick={() => setActiveId(lessons[idx + 1]?.id)}
          >
            Next lesson →
          </button>
        </div>
      </div>
    </div>
  );
}
