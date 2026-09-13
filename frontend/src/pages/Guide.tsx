import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import TopBar from "../components/TopBar";
import GuideView from "../components/GuideView";
import ArchitectureView from "../components/ArchitectureView";
import DataFlowView from "../components/DataFlowView";
import SchemaView from "../components/SchemaView";
import SandboxView from "../components/SandboxView";
import { getAnalysis } from "../api";
import { exportGuidePdf } from "../pdf";
import type { AnalysisResult } from "../types";

export default function Guide() {
  const { id, tab } = useParams();
  const nav = useNavigate();
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState("");
  const activeTab = tab || "";

  useEffect(() => {
    if (!id) return;
    getAnalysis(id).then(setResult).catch((e) => setError((e as Error).message));
  }, [id]);

  const hasSchema = !!result?.schema?.tables?.length;
  const tabs = [
    { key: "", label: "My Guide" },
    { key: "architecture", label: "Architecture" },
    { key: "dataflow", label: "Data Flow" },
    ...(hasSchema ? [{ key: "schema", label: "Schema" }] : []),
    { key: "sandbox", label: "App Tour" },
  ];

  const exportPdf = () => {
    if (result) exportGuidePdf(result);
  };

  if (error) {
    return (
      <>
        <TopBar />
        <div className="glass empty" style={{ marginTop: 40 }}>{error}</div>
      </>
    );
  }
  if (!result) {
    return (
      <>
        <TopBar />
        <div className="empty"><span className="spinner" /> Loading your guide…</div>
      </>
    );
  }

  return (
    <>
      <TopBar
        sub={`${result.repo.owner}/${result.repo.name}`}
        nav={tabs.map((t) => ({
          label: t.label,
          to: `/guide/${id}${t.key ? "/" + t.key : ""}`,
          active: activeTab === t.key,
        }))}
        right={<button className="btn" onClick={exportPdf}>⤓ Export PDF</button>}
      />

      <div className="tab-bar">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`chip ${activeTab === t.key ? "on" : ""}`}
            onClick={() => nav(`/guide/${id}${t.key ? "/" + t.key : ""}`)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "" && <GuideView result={result} />}
      {activeTab === "architecture" && <ArchitectureView arch={result.architecture} />}
      {activeTab === "dataflow" && <DataFlowView flow={result.dataflow} />}
      {activeTab === "schema" && <SchemaView schema={result.schema} />}
      {activeTab === "sandbox" && <SandboxView sandbox={result.sandbox} />}
    </>
  );
}
