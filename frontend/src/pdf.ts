import { jsPDF } from "jspdf";
import type { AnalysisResult } from "./types";

const MARGIN = 48;
const LINE = 15;

export function exportGuidePdf(result: AnalysisResult): void {
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const maxW = pageW - MARGIN * 2;
  let y = MARGIN;

  const ensure = (needed = LINE) => {
    if (y + needed > pageH - MARGIN) {
      doc.addPage();
      y = MARGIN;
    }
  };

  const text = (
    s: string,
    opts: { size?: number; bold?: boolean; color?: [number, number, number]; gap?: number } = {}
  ) => {
    const { size = 11, bold = false, color = [30, 35, 40], gap = 4 } = opts;
    doc.setFont("helvetica", bold ? "bold" : "normal");
    doc.setFontSize(size);
    doc.setTextColor(color[0], color[1], color[2]);
    const lines = doc.splitTextToSize(s || "", maxW) as string[];
    for (const ln of lines) {
      ensure(size + 2);
      doc.text(ln, MARGIN, y);
      y += size + 2;
    }
    y += gap;
  };

  const rule = () => {
    ensure(10);
    doc.setDrawColor(210, 215, 220);
    doc.line(MARGIN, y, pageW - MARGIN, y);
    y += 12;
  };

  // Cover
  doc.setFillColor(13, 17, 23);
  doc.rect(0, 0, pageW, 120, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(24);
  doc.text("GitHubIQ", MARGIN, 60);
  doc.setFontSize(13);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(180, 190, 200);
  doc.text(`Onboarding guide — ${result.repo.owner}/${result.repo.name}`, MARGIN, 86);
  y = 150;

  text(result.guide.title || "Onboarding guide", { size: 18, bold: true });
  text(result.guide.intro, { color: [90, 100, 110] });

  // Research overview
  if (result.research?.what) {
    rule();
    text("Overview", { size: 14, bold: true, color: [9, 105, 218] });
    text(`What it is: ${result.research.what}`);
    if (result.research.does) text(`What it does: ${result.research.does}`);
    if (result.research.how) text(`How it works: ${result.research.how}`);
  }

  // Components
  if (result.research?.components?.length) {
    rule();
    text("Components", { size: 14, bold: true, color: [9, 105, 218] });
    for (const c of result.research.components) {
      text(`${c.name}  (${c.kind})`, { bold: true, gap: 1 });
      if (c.tech?.length) text(`Tech: ${c.tech.join(", ")}`, { size: 9.5, color: [120, 128, 138], gap: 1 });
      text(c.responsibility, { color: [80, 88, 98] });
    }
  }

  // Lessons
  if (result.guide.lessons?.length) {
    rule();
    text("Guide", { size: 14, bold: true, color: [9, 105, 218] });
    let section = "";
    for (const l of result.guide.lessons) {
      if (l.section !== section) {
        section = l.section;
        text(section.toUpperCase(), { size: 10, bold: true, color: [130, 80, 223], gap: 2 });
      }
      text(l.title, { bold: true, size: 12, gap: 1 });
      text(l.body || l.summary, { color: [70, 78, 88] });
    }
  }

  // Data flow
  if (result.dataflow?.steps?.length) {
    rule();
    text(`Data flow — ${result.dataflow.title}`, { size: 14, bold: true, color: [9, 105, 218] });
    for (const s of result.dataflow.steps) {
      text(`${s.index}. ${s.actor} — ${s.label} [${s.kind}]`, { bold: true, size: 11, gap: 1 });
      if (s.detail) text(s.detail, { size: 10, color: [90, 98, 108] });
    }
  }

  // Schema
  if (result.schema?.tables?.length) {
    rule();
    text("Database schema", { size: 14, bold: true, color: [9, 105, 218] });
    for (const t of result.schema.tables) {
      const cols = t.columns
        .map((c) => `${c.name}: ${c.type}${c.key ? ` (${c.key})` : ""}`)
        .join(", ");
      text(t.name, { bold: true, size: 11, gap: 1 });
      text(cols, { size: 9.5, color: [90, 98, 108] });
    }
  }

  doc.save(`githubiq-${result.repo.name || "guide"}.pdf`);
}
