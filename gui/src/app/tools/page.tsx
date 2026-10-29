"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import {
  getResumeDocuments,
  getResumeDocument,
  saveResumeDocument,
  renderResumeDocuments,
  getResumeFileUrl,
  type ResumeDocument,
  type DocumentDetail,
  type PageBudgetMetrics,
  type RenderResponse,
  type RenderResultRecord,
} from "@/lib/api";

// ── Navigation & Tool Identifiers ────────────────────────────────────────────

// Available primary tools hosted on the Tools suite
type ActiveToolKey = "resume_engine" | "podcast_gen" | "web_scraper" | "youtube_transcript";

interface ToolTabMeta {
  id: ActiveToolKey;
  label: string;
  icon: string;
  status: "active" | "planned";
  tagline: string;
}

const TOOL_TABS: ToolTabMeta[] = [
  {
    id: "resume_engine",
    label: "Resume Engine",
    icon: "📄",
    status: "active",
    tagline: "Compile markdown resumes & cover letters to PDF/DOCX with real-time page budget analysis.",
  },
  {
    id: "podcast_gen",
    label: "Podcast Generator",
    icon: "🎙️",
    status: "planned",
    tagline: "Synthesize long-form markdown notes into multi-speaker MP3 podcasts via edge-tts.",
  },
  {
    id: "web_scraper",
    label: "Web Scraper",
    icon: "🌐",
    status: "planned",
    tagline: "Scrape external web URLs and extract clean markdown directly into the Vault.",
  },
  {
    id: "youtube_transcript",
    label: "YouTube Transcriber",
    icon: "📺",
    status: "planned",
    tagline: "Download and format complete video transcripts into structured Obsidian notes.",
  },
];

// Document inspection sub-view tabs inside the active Resume Engine studio
type StudioViewTab = "metrics" | "editor" | "preview";

// Filter category options for the document explorer
type CategoryFilter = "all" | "resume" | "cover_letter";


// ── Helper: Verdict Styling & Semantic Labels ────────────────────────────────

function getVerdictBadge(verdict?: string) {
  switch (verdict) {
    case "GOOD FIT":
      return {
        icon: "✅",
        label: "Good Fit",
        className: "bg-accent-emerald/15 text-accent-emerald border-accent-emerald/30",
        description: "Optimal length with comfortable whitespace.",
      };
    case "TIGHT FIT":
      return {
        icon: "🎯",
        label: "Tight Fit",
        className: "bg-accent-amber/15 text-accent-amber border-accent-amber/30",
        description: "Maximizes single-page budget with zero overflow spill.",
      };
    case "ROOM":
      return {
        icon: "📝",
        label: "Room Remaining",
        className: "bg-accent-cyan/15 text-accent-cyan border-accent-cyan/30",
        description: "Moderate fill; space available for additional bullet points.",
      };
    case "UNDERFILL":
      return {
        icon: "⚠️",
        label: "Underfill",
        className: "bg-accent-amber/20 text-accent-amber border-accent-amber/40",
        description: "Page is less than 60% full; consider expanding experience or skills.",
      };
    case "OVERFLOW":
      return {
        icon: "🔴",
        label: "Overflow",
        className: "bg-accent-rose/15 text-accent-rose border-accent-rose/30",
        description: "Content spilled onto an additional page. Needs trimming.",
      };
    default:
      return {
        icon: "⚪",
        label: "Unmeasured",
        className: "bg-bg-surface text-text-muted border-border-subtle",
        description: "Render document to measure page budget geometry.",
      };
  }
}


// ── Main Tools Page Component ────────────────────────────────────────────────

export default function ToolsPage() {
  // activeTool: Top-level switcher among available Nexus operational tools
  const [activeTool, setActiveTool] = useState<ActiveToolKey>("resume_engine");

  // ── Resume Engine State ────────────────────────────────────────────────────
  const [documents, setDocuments] = useState<ResumeDocument[]>([]);
  const [selectedDocPath, setSelectedDocPath] = useState<string | null>(null);
  const [activeDetail, setActiveDetail] = useState<DocumentDetail | null>(null);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());

  // Editorial and view state
  const [studioTab, setStudioTab] = useState<StudioViewTab>("metrics");
  const [editorContent, setEditorContent] = useState<string>("");
  const [isEditorDirty, setIsEditorDirty] = useState<boolean>(false);
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Loading and execution indicators
  const [loadingDocs, setLoadingDocs] = useState<boolean>(true);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [savingDoc, setSavingDoc] = useState<boolean>(false);
  const [rendering, setRendering] = useState<boolean>(false);
  const [renderStatusMsg, setRenderStatusMsg] = useState<string>("");
  const [lastRenderResponse, setLastRenderResponse] = useState<RenderResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successToast, setSuccessToast] = useState<string | null>(null);
  const [pdfPreviewKey, setPdfPreviewKey] = useState<number>(Date.now());

  // ── Initial Document Scan ──────────────────────────────────────────────────
  const fetchDocuments = useCallback(async (selectPathAfter?: string) => {
    try {
      setLoadingDocs(true);
      setErrorMessage(null);
      const docs = await getResumeDocuments();
      setDocuments(docs);

      if (docs.length > 0) {
        // If a target path was explicitly requested to be selected, prioritize it
        if (selectPathAfter && docs.some((d) => d.path === selectPathAfter)) {
          setSelectedDocPath(selectPathAfter);
        } else if (!selectedDocPath || !docs.some((d) => d.path === selectedDocPath)) {
          setSelectedDocPath(docs[0].path);
        }
      } else {
        setSelectedDocPath(null);
        setActiveDetail(null);
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to load documents.");
    } finally {
      setLoadingDocs(false);
    }
  }, [selectedDocPath]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // ── Load Active Document Detail ────────────────────────────────────────────
  useEffect(() => {
    if (!selectedDocPath) {
      setActiveDetail(null);
      setEditorContent("");
      setIsEditorDirty(false);
      return;
    }

    let isCancelled = false;
    async function loadDetail(path: string) {
      try {
        setLoadingDetail(true);
        const detail = await getResumeDocument(path);
        if (!isCancelled) {
          setActiveDetail(detail);
          setEditorContent(detail.content);
          setIsEditorDirty(false);
        }
      } catch (err) {
        if (!isCancelled) {
          setErrorMessage(err instanceof Error ? err.message : "Failed to load document content.");
        }
      } finally {
        if (!isCancelled) {
          setLoadingDetail(false);
        }
      }
    }

    loadDetail(selectedDocPath);
    return () => {
      isCancelled = true;
    };
  }, [selectedDocPath]);

  // ── Filtered Documents List ────────────────────────────────────────────────
  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      // Category filter
      if (categoryFilter !== "all" && doc.category !== categoryFilter) {
        return false;
      }
      // Search query filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        return (
          doc.name.toLowerCase().includes(query) ||
          doc.relative_path.toLowerCase().includes(query)
        );
      }
      return true;
    });
  }, [documents, categoryFilter, searchQuery]);

  // ── Multi-select Handlers ──────────────────────────────────────────────────
  const toggleSelectDoc = (path: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedPaths.size === filteredDocuments.length) {
      setSelectedPaths(new Set());
    } else {
      setSelectedPaths(new Set(filteredDocuments.map((d) => d.path)));
    }
  };

  // ── Save Document Content ──────────────────────────────────────────────────
  const handleSaveDocument = async () => {
    if (!selectedDocPath) return;
    try {
      setSavingDoc(true);
      const updated = await saveResumeDocument(selectedDocPath, editorContent);
      setActiveDetail(updated);
      setIsEditorDirty(false);
      setSuccessToast("Document saved to disk.");
      setTimeout(() => setSuccessToast(null), 3000);
      // Refresh documents list to sync modified timestamp
      fetchDocuments(selectedDocPath);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to save document.");
    } finally {
      setSavingDoc(false);
    }
  };

  // ── Render Handlers ────────────────────────────────────────────────────────
  const handleRender = async (pathsToRender: string[], formats: ("pdf" | "docx")[] = ["pdf", "docx"]) => {
    if (pathsToRender.length === 0) return;

    try {
      setRendering(true);
      setRenderStatusMsg(
        pathsToRender.length === 1
          ? "Compiling document and measuring geometry..."
          : `Compiling ${pathsToRender.length} documents...`
      );
      setErrorMessage(null);

      const resp = await renderResumeDocuments(pathsToRender, formats);
      setLastRenderResponse(resp);

      if (resp.success) {
        setSuccessToast(
          pathsToRender.length === 1
            ? "Compilation complete! Artifacts saved & copied to Downloads."
            : `Batch compilation complete (${resp.results.length} files).`
        );
        setTimeout(() => setSuccessToast(null), 5000);
        // Force PDF iframe refresh
        setPdfPreviewKey(Date.now());
        // Reload documents list & active detail to pick up new metrics and artifact presence
        await fetchDocuments(selectedDocPath || undefined);
        if (selectedDocPath) {
          const updatedDetail = await getResumeDocument(selectedDocPath);
          setActiveDetail(updatedDetail);
        }
      } else {
        setErrorMessage(resp.error || "Compilation failed. Check execution logs.");
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Compilation request failed.");
    } finally {
      setRendering(false);
      setRenderStatusMsg("");
    }
  };

  // Quick single-document render trigger
  const handleRenderActiveDoc = (formats: ("pdf" | "docx")[] = ["pdf", "docx"]) => {
    if (selectedDocPath) {
      handleRender([selectedDocPath], formats);
    }
  };

  // Batch render of selected documents
  const handleRenderSelected = () => {
    if (selectedPaths.size > 0) {
      handleRender(Array.from(selectedPaths), ["pdf", "docx"]);
    }
  };

  // Render all documents in portfolio
  const handleRenderAll = () => {
    handleRender(["all"], ["pdf", "docx"]);
  };

  // Active document's metrics (either from activeDetail or documents array fallback)
  const activeMetrics: PageBudgetMetrics | null | undefined =
    activeDetail?.metrics ??
    documents.find((d) => d.path === selectedDocPath)?.metrics;

  const verdictMeta = getVerdictBadge(activeMetrics?.verdict);

  return (
    <div className="flex flex-col min-h-screen bg-bg-primary text-text-primary p-6 lg:p-8 max-w-[1700px] mx-auto w-full">
      {/* ── Page Header & Tool Switcher ────────────────────────── */}
      <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border-subtle pb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <span className="text-2xl">🛠️</span>
            <h1 className="text-2xl font-bold tracking-tight gradient-text">
              Nexus Tools Suite
            </h1>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20 font-medium">
              v1.0
            </span>
          </div>
          <p className="text-sm text-text-secondary">
            Operational compilers, document engines, and dedicated production utilities.
          </p>
        </div>

        {/* Global Tool Tab Switcher */}
        <div className="flex items-center gap-2 p-1.5 rounded-xl bg-bg-secondary border border-border-subtle overflow-x-auto">
          {TOOL_TABS.map((tab) => {
            const isTabActive = activeTool === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => tab.status === "active" && setActiveTool(tab.id)}
                disabled={tab.status !== "active"}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium transition-all shrink-0 ${
                  isTabActive
                    ? "bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30 shadow-sm"
                    : tab.status === "active"
                    ? "text-text-secondary hover:text-text-primary hover:bg-bg-surface"
                    : "text-text-muted opacity-50 cursor-not-allowed"
                }`}
                title={tab.tagline}
              >
                <span>{tab.icon}</span>
                <span>{tab.label}</span>
                {tab.status !== "active" && (
                  <span className="text-[0.6rem] uppercase tracking-wider px-1.5 py-0.5 rounded bg-bg-surface text-text-muted">
                    Soon
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </header>

      {/* ── Toast Notifications ───────────────────────────────── */}
      {successToast && (
        <div className="mb-4 p-3 rounded-xl bg-accent-emerald/10 border border-accent-emerald/30 text-accent-emerald text-sm flex items-center justify-between animate-fade-in-up">
          <div className="flex items-center gap-2">
            <span>✓</span>
            <span>{successToast}</span>
          </div>
          <button
            onClick={() => setSuccessToast(null)}
            className="text-accent-emerald/70 hover:text-accent-emerald text-xs"
          >
            ✕
          </button>
        </div>
      )}

      {errorMessage && (
        <div className="mb-4 p-3 rounded-xl bg-accent-rose/10 border border-accent-rose/30 text-accent-rose text-sm flex items-center justify-between animate-fade-in-up">
          <div className="flex items-center gap-2">
            <span>⚠</span>
            <span>{errorMessage}</span>
          </div>
          <button
            onClick={() => setErrorMessage(null)}
            className="text-accent-rose/70 hover:text-accent-rose text-xs"
          >
            ✕
          </button>
        </div>
      )}

      {/* ── Main Tool Canvas: Resume Engine ────────────────────── */}
      {activeTool === "resume_engine" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* ═══════════════════════════════════════════════════════
              LEFT COLUMN: Portfolio Documents Explorer (4 Cols)
              ═══════════════════════════════════════════════════════ */}
          <aside className="lg:col-span-4 flex flex-col gap-4">
            <div className="glass-card p-4 flex flex-col gap-3">
              {/* Explorer Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-base">📁</span>
                  <h2 className="text-sm font-semibold text-text-primary tracking-wide">
                    Portfolio Documents
                  </h2>
                </div>
                <button
                  onClick={() => fetchDocuments()}
                  disabled={loadingDocs}
                  className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-surface text-xs transition-colors"
                  title="Rescan disk for newly added files"
                >
                  🔄
                </button>
              </div>

              {/* Filter Tabs */}
              <div className="flex rounded-lg bg-bg-surface p-1 text-xs gap-1">
                {(["all", "resume", "cover_letter"] as CategoryFilter[]).map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setCategoryFilter(cat)}
                    className={`flex-1 py-1.5 rounded-md font-medium transition-colors ${
                      categoryFilter === cat
                        ? "bg-bg-card text-accent-cyan shadow-xs"
                        : "text-text-secondary hover:text-text-primary"
                    }`}
                  >
                    {cat === "all"
                      ? `All (${documents.length})`
                      : cat === "resume"
                      ? `Resumes (${documents.filter((d) => d.category === "resume").length})`
                      : `Letters (${documents.filter((d) => d.category === "cover_letter").length})`}
                  </button>
                ))}
              </div>

              {/* Search Bar */}
              <div className="relative">
                <input
                  type="text"
                  placeholder="Filter documents..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-bg-surface/80 border border-border-subtle rounded-lg px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-cyan/50"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery("")}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary text-xs"
                  >
                    ✕
                  </button>
                )}
              </div>

              {/* Batch Selection Bar */}
              <div className="flex items-center justify-between text-xs pt-1 border-t border-border-subtle/50 text-text-secondary">
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={
                      filteredDocuments.length > 0 &&
                      selectedPaths.size === filteredDocuments.length
                    }
                    onChange={handleSelectAll}
                    className="rounded border-border-subtle text-accent-cyan focus:ring-0"
                  />
                  <span>Select All ({filteredDocuments.length})</span>
                </label>

                {selectedPaths.size > 0 && (
                  <button
                    onClick={handleRenderSelected}
                    disabled={rendering}
                    className="px-2.5 py-1 rounded-md bg-accent-cyan/15 text-accent-cyan hover:bg-accent-cyan/25 border border-accent-cyan/30 text-xs font-medium transition-colors flex items-center gap-1.5"
                  >
                    <span>⚡</span>
                    <span>Render Selected ({selectedPaths.size})</span>
                  </button>
                )}
              </div>

              {/* Document Items List */}
              <div className="flex flex-col gap-2 max-h-[calc(100vh-340px)] overflow-y-auto pr-1">
                {loadingDocs ? (
                  <div className="py-8 text-center text-xs text-text-muted">
                    Scanning portfolio directory...
                  </div>
                ) : filteredDocuments.length === 0 ? (
                  <div className="py-8 text-center text-xs text-text-muted">
                    No documents found matching filter.
                  </div>
                ) : (
                  filteredDocuments.map((doc) => {
                    const isSelected = selectedDocPath === doc.path;
                    const isChecked = selectedPaths.has(doc.path);
                    const docVerdict = getVerdictBadge(doc.metrics?.verdict);

                    return (
                      <div
                        key={doc.path}
                        onClick={() => setSelectedDocPath(doc.path)}
                        className={`p-3 rounded-xl border transition-all cursor-pointer relative group ${
                          isSelected
                            ? "bg-accent-cyan/10 border-accent-cyan/40 shadow-sm shadow-accent-cyan/10"
                            : "bg-bg-surface/60 border-border-subtle hover:bg-bg-surface hover:border-border-accent/40"
                        }`}
                      >
                        <div className="flex items-start gap-2.5">
                          {/* Checkbox for batch rendering */}
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onClick={(e) => toggleSelectDoc(doc.path, e)}
                            onChange={() => {}}
                            className="mt-1 rounded border-border-subtle text-accent-cyan focus:ring-0 shrink-0"
                          />

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-1 mb-1">
                              <span
                                className={`text-xs font-semibold truncate ${
                                  isSelected ? "text-accent-cyan" : "text-text-primary"
                                }`}
                                title={doc.name}
                              >
                                {doc.name}
                              </span>
                            </div>

                            {/* Tags and Status Badges */}
                            <div className="flex items-center flex-wrap gap-1.5 mt-2">
                              {/* Category Badge */}
                              <span
                                className={`text-[0.65rem] px-2 py-0.5 rounded font-medium ${
                                  doc.category === "resume"
                                    ? "bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20"
                                    : "bg-accent-violet/10 text-accent-violet border border-accent-violet/20"
                                }`}
                              >
                                {doc.category_label}
                              </span>

                              {/* Output Artifact Presence */}
                              <span
                                className={`text-[0.65rem] px-1.5 py-0.5 rounded font-mono ${
                                  doc.has_pdf
                                    ? "bg-accent-emerald/10 text-accent-emerald border border-accent-emerald/20"
                                    : "bg-bg-surface text-text-muted border border-border-subtle opacity-50"
                                }`}
                                title={doc.has_pdf ? "PDF compiled on disk" : "PDF not yet rendered"}
                              >
                                PDF
                              </span>

                              <span
                                className={`text-[0.65rem] px-1.5 py-0.5 rounded font-mono ${
                                  doc.has_docx
                                    ? "bg-accent-violet/10 text-accent-violet border border-accent-violet/20"
                                    : "bg-bg-surface text-text-muted border border-border-subtle opacity-50"
                                }`}
                                title={doc.has_docx ? "DOCX compiled on disk" : "DOCX not yet rendered"}
                              >
                                DOCX
                              </span>

                              {/* Verdict Badge if metrics present */}
                              {doc.metrics?.verdict && (
                                <span
                                  className={`text-[0.65rem] px-2 py-0.5 rounded-full border font-medium ml-auto flex items-center gap-1 ${docVerdict.className}`}
                                  title={`${docVerdict.label}: ${doc.metrics.lastPageFillPct}% fill on page ${doc.metrics.pages}`}
                                >
                                  <span>{docVerdict.icon}</span>
                                  <span>{doc.metrics.verdict}</span>
                                  {doc.metrics.lastPageFillPct !== undefined && (
                                    <span className="opacity-80">({doc.metrics.lastPageFillPct}%)</span>
                                  )}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Bottom Quick Action: Compile All */}
              <div className="pt-2 border-t border-border-subtle">
                <button
                  onClick={handleRenderAll}
                  disabled={rendering || documents.length === 0}
                  className="w-full py-2 px-3 rounded-lg bg-bg-surface hover:bg-bg-surface/80 border border-border-subtle text-xs font-medium text-text-secondary hover:text-text-primary transition-colors flex items-center justify-center gap-2"
                >
                  <span>🚀</span>
                  <span>Compile Entire Portfolio ({documents.length} Files)</span>
                </button>
              </div>
            </div>
          </aside>

          {/* ═══════════════════════════════════════════════════════
              RIGHT COLUMN: Document Studio & Compiler (8 Cols)
              ═══════════════════════════════════════════════════════ */}
          <main className="lg:col-span-8 flex flex-col gap-4">
            {selectedDocPath && activeDetail ? (
              <div className="glass-card p-6 flex flex-col gap-6">
                {/* ── Studio Header & Primary Action Bar ───────────── */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border-subtle pb-5">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs px-2 py-0.5 rounded bg-bg-surface text-accent-cyan border border-border-subtle font-mono uppercase">
                        {activeDetail.relative_path.startsWith("Vault")
                          ? activeDetail.relative_path.split("/").slice(-2)[0]
                          : "Portfolio"}
                      </span>
                      <h2 className="text-xl font-bold text-text-primary truncate" title={activeDetail.name}>
                        {activeDetail.name}
                      </h2>
                    </div>
                    <p className="text-xs text-text-muted font-mono truncate" title={activeDetail.path}>
                      {activeDetail.relative_path}
                    </p>
                  </div>

                  {/* Actions Bar */}
                  <div className="flex items-center flex-wrap gap-2 shrink-0">
                    {/* Primary Compiler Button */}
                    <button
                      onClick={() => handleRenderActiveDoc(["pdf", "docx"])}
                      disabled={rendering}
                      className="px-4 py-2 rounded-xl bg-gradient-to-r from-accent-cyan to-accent-cyan/80 text-bg-primary font-semibold text-xs shadow-md shadow-accent-cyan/20 hover:opacity-95 transition-opacity flex items-center gap-2 disabled:opacity-50"
                    >
                      <span>{rendering ? "⏳" : "⚡"}</span>
                      <span>{rendering ? "Compiling..." : "Render Document"}</span>
                    </button>

                    {/* Format Options Dropdown / Specific Buttons */}
                    <button
                      onClick={() => handleRenderActiveDoc(["pdf"])}
                      disabled={rendering}
                      className="px-3 py-2 rounded-xl bg-bg-surface hover:bg-bg-surface/80 border border-border-subtle text-xs text-text-secondary hover:text-text-primary transition-colors"
                      title="Render PDF format only"
                    >
                      PDF Only
                    </button>

                    <button
                      onClick={() => handleRenderActiveDoc(["docx"])}
                      disabled={rendering}
                      className="px-3 py-2 rounded-xl bg-bg-surface hover:bg-bg-surface/80 border border-border-subtle text-xs text-text-secondary hover:text-text-primary transition-colors"
                      title="Render DOCX format only"
                    >
                      DOCX Only
                    </button>

                    {/* Download PDF Button */}
                    {activeDetail.has_pdf && (
                      <a
                        href={getResumeFileUrl(activeDetail.path, "pdf", true)}
                        download
                        className="px-3 py-2 rounded-xl bg-accent-emerald/15 hover:bg-accent-emerald/25 border border-accent-emerald/30 text-accent-emerald text-xs font-medium transition-colors flex items-center gap-1.5"
                        title="Download compiled .pdf file"
                      >
                        <span>📥</span>
                        <span>PDF</span>
                      </a>
                    )}

                    {/* Download DOCX Button */}
                    {activeDetail.has_docx && (
                      <a
                        href={getResumeFileUrl(activeDetail.path, "docx", true)}
                        download
                        className="px-3 py-2 rounded-xl bg-accent-violet/15 hover:bg-accent-violet/25 border border-accent-violet/30 text-accent-violet text-xs font-medium transition-colors flex items-center gap-1.5"
                        title="Download compiled .docx file"
                      >
                        <span>📥</span>
                        <span>DOCX</span>
                      </a>
                    )}
                  </div>
                </div>

                {/* Rendering Active Banner */}
                {rendering && (
                  <div className="p-3 rounded-xl bg-accent-cyan/10 border border-accent-cyan/30 text-accent-cyan text-xs flex items-center gap-2 animate-pulse">
                    <span>⚡</span>
                    <span>{renderStatusMsg || "Compiling document with headless Chromium..."}</span>
                  </div>
                )}

                {/* ── Studio Navigation Tabs ───────────────────────── */}
                <div className="flex items-center justify-between border-b border-border-subtle pb-2">
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setStudioTab("metrics")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                        studioTab === "metrics"
                          ? "bg-bg-surface text-accent-cyan border border-border-accent/40"
                          : "text-text-secondary hover:text-text-primary"
                      }`}
                    >
                      📐 Page Budget & Metrics
                    </button>
                    <button
                      onClick={() => setStudioTab("editor")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 ${
                        studioTab === "editor"
                          ? "bg-bg-surface text-accent-cyan border border-border-accent/40"
                          : "text-text-secondary hover:text-text-primary"
                      }`}
                    >
                      <span>✏️ Markdown Editor</span>
                      {isEditorDirty && (
                        <span className="w-1.5 h-1.5 rounded-full bg-accent-amber" title="Unsaved changes" />
                      )}
                    </button>
                    <button
                      onClick={() => setStudioTab("preview")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                        studioTab === "preview"
                          ? "bg-bg-surface text-accent-cyan border border-border-accent/40"
                          : "text-text-secondary hover:text-text-primary"
                      }`}
                    >
                      👁️ Live PDF View
                    </button>
                  </div>

                  {/* Quick word/line counts */}
                  <div className="text-[0.7rem] font-mono text-text-muted flex items-center gap-3">
                    <span>{activeDetail.lines_count} lines</span>
                    <span>•</span>
                    <span>{activeDetail.words_count} words</span>
                  </div>
                </div>

                {/* ── TAB 1: Page Budget & Geometry Metrics ─────────── */}
                {studioTab === "metrics" && (
                  <div className="flex flex-col gap-6">
                    {/* Visual Metric Scorecard Grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                      {/* Metric 1: Verdict Card */}
                      <div className="p-4 rounded-xl bg-bg-surface/70 border border-border-subtle flex flex-col justify-between">
                        <span className="text-[0.7rem] uppercase tracking-wider text-text-muted font-medium mb-1">
                          Budget Verdict
                        </span>
                        <div className="flex items-center gap-2 my-1">
                          <span className="text-xl">{verdictMeta.icon}</span>
                          <span className="text-base font-bold text-text-primary">
                            {verdictMeta.label}
                          </span>
                        </div>
                        <p className="text-[0.7rem] text-text-secondary leading-snug">
                          {verdictMeta.description}
                        </p>
                      </div>

                      {/* Metric 2: Page Count */}
                      <div className="p-4 rounded-xl bg-bg-surface/70 border border-border-subtle flex flex-col justify-between">
                        <span className="text-[0.7rem] uppercase tracking-wider text-text-muted font-medium mb-1">
                          Page Count
                        </span>
                        <div className="flex items-baseline gap-1 my-1">
                          <span className="text-2xl font-bold text-accent-cyan">
                            {activeMetrics?.pages ?? (activeDetail.has_pdf ? "1" : "—")}
                          </span>
                          <span className="text-xs text-text-muted">
                            {activeMetrics?.pages === 1 ? "Page (Optimal)" : "Pages"}
                          </span>
                        </div>
                        <p className="text-[0.7rem] text-text-secondary">
                          Standard single-page target: 1 page.
                        </p>
                      </div>

                      {/* Metric 3: Page Fill % */}
                      <div className="p-4 rounded-xl bg-bg-surface/70 border border-border-subtle flex flex-col justify-between">
                        <span className="text-[0.7rem] uppercase tracking-wider text-text-muted font-medium mb-1">
                          Last Page Fill
                        </span>
                        <div className="flex items-baseline gap-1 my-1">
                          <span className="text-2xl font-bold text-text-primary">
                            {activeMetrics?.lastPageFillPct !== undefined
                              ? `${activeMetrics.lastPageFillPct}%`
                              : "—"}
                          </span>
                        </div>
                        {/* Progress Meter Bar */}
                        <div className="w-full h-1.5 rounded-full bg-bg-secondary overflow-hidden mt-1">
                          <div
                            className={`h-full transition-all duration-500 ${
                              (activeMetrics?.lastPageFillPct ?? 0) > 100
                                ? "bg-accent-rose"
                                : (activeMetrics?.lastPageFillPct ?? 0) >= 95
                                ? "bg-accent-amber"
                                : (activeMetrics?.lastPageFillPct ?? 0) >= 60
                                ? "bg-accent-emerald"
                                : "bg-accent-cyan"
                            }`}
                            style={{
                              width: `${Math.min(activeMetrics?.lastPageFillPct ?? 0, 100)}%`,
                            }}
                          />
                        </div>
                      </div>

                      {/* Metric 4: Headroom & Bullets Remaining */}
                      <div className="p-4 rounded-xl bg-bg-surface/70 border border-border-subtle flex flex-col justify-between">
                        <span className="text-[0.7rem] uppercase tracking-wider text-text-muted font-medium mb-1">
                          Headroom / Trim Advice
                        </span>
                        <div className="my-1">
                          {activeMetrics?.approxBulletsRemaining !== undefined ? (
                            activeMetrics.approxBulletsRemaining > 0 ? (
                              <span className="text-sm font-semibold text-accent-cyan">
                                ~{activeMetrics.approxBulletsRemaining} bullets fit
                              </span>
                            ) : (activeMetrics.lastPageFillPct ?? 0) > 100 ? (
                              <span className="text-sm font-semibold text-accent-rose">
                                Trim ~{Math.ceil(Math.abs(activeMetrics.roomRemainingPx || 0) / 45)} bullets
                              </span>
                            ) : (
                              <span className="text-sm font-semibold text-accent-emerald">
                                Zero spill / Max density
                              </span>
                            )
                          ) : (
                            <span className="text-sm text-text-muted">No measurements</span>
                          )}
                        </div>
                        <p className="text-[0.7rem] text-text-secondary">
                          {activeMetrics?.roomRemainingPx !== undefined
                            ? `${activeMetrics.roomRemainingPx}px remaining on last page`
                            : "Click Render Document to calculate."}
                        </p>
                      </div>
                    </div>

                    {/* Output Artifacts & Download Bar */}
                    <div className="p-4 rounded-xl bg-bg-surface/40 border border-border-subtle flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-text-primary">Compiled Output:</span>
                          <span className="text-text-muted font-mono">{activeDetail.path}</span>
                        </div>
                        <div className="flex items-center gap-2 text-text-secondary">
                          <span>Downloads Mirror:</span>
                          <span className="font-mono text-accent-cyan">
                            ~/Downloads/{activeDetail.name}.pdf
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {activeDetail.has_pdf && (
                          <a
                            href={getResumeFileUrl(activeDetail.path, "pdf", true)}
                            download
                            className="px-3 py-1.5 rounded-lg bg-bg-surface hover:bg-bg-surface/80 border border-border-subtle text-accent-cyan font-medium transition-colors flex items-center gap-1.5"
                          >
                            <span>📥</span>
                            <span>Download PDF</span>
                          </a>
                        )}
                        {activeDetail.has_docx && (
                          <a
                            href={getResumeFileUrl(activeDetail.path, "docx", true)}
                            download
                            className="px-3 py-1.5 rounded-lg bg-bg-surface hover:bg-bg-surface/80 border border-border-subtle text-accent-violet font-medium transition-colors flex items-center gap-1.5"
                          >
                            <span>📥</span>
                            <span>Download DOCX</span>
                          </a>
                        )}
                      </div>
                    </div>

                    {/* Compiler Console Logs Drawer */}
                    <div className="rounded-xl bg-bg-secondary border border-border-subtle overflow-hidden">
                      <div className="px-4 py-2 bg-bg-surface/50 border-b border-border-subtle flex items-center justify-between text-xs text-text-secondary">
                        <div className="flex items-center gap-2">
                          <span className="text-accent-cyan">❯_</span>
                          <span className="font-medium font-mono">Compiler Execution Stream</span>
                        </div>
                        <span className="text-[0.65rem] text-text-muted">
                          {lastRenderResponse ? `Exit Code: ${lastRenderResponse.exit_code}` : "Awaiting execution"}
                        </span>
                      </div>
                      <div className="p-4 font-mono text-[0.75rem] text-text-secondary leading-relaxed max-h-56 overflow-y-auto whitespace-pre-wrap select-text">
                        {lastRenderResponse?.logs ? (
                          lastRenderResponse.logs
                        ) : activeMetrics ? (
                          `Last measured at: ${activeMetrics.measured_at || "Cached"}\nHeight: ${activeMetrics.contentHeightPx}px / Single Page Limit: ${activeMetrics.pageHeightPx}px\nFill: ${activeMetrics.lastPageFillPct}%\nVerdict: ${activeMetrics.verdict}`
                        ) : (
                          "Ready to compile. Click 'Render Document' above to run the headless Playwright and DOCX compiler pipeline."
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* ── TAB 2: In-Browser Markdown Editor ────────────── */}
                {studioTab === "editor" && (
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between text-xs text-text-secondary">
                      <p>
                        Edit markdown source directly. Changes write directly to the Vault on save.
                      </p>
                      <div className="flex items-center gap-2">
                        {isEditorDirty && (
                          <button
                            onClick={() => {
                              setEditorContent(activeDetail.content);
                              setIsEditorDirty(false);
                            }}
                            className="px-2.5 py-1 rounded-md text-text-muted hover:text-text-primary text-xs"
                          >
                            Discard
                          </button>
                        )}
                        <button
                          onClick={handleSaveDocument}
                          disabled={savingDoc || !isEditorDirty}
                          className="px-3.5 py-1.5 rounded-lg bg-accent-emerald/20 hover:bg-accent-emerald/30 border border-accent-emerald/40 text-accent-emerald font-semibold text-xs transition-colors flex items-center gap-1.5 disabled:opacity-40"
                        >
                          <span>{savingDoc ? "⏳" : "💾"}</span>
                          <span>{savingDoc ? "Saving..." : "Save Markdown"}</span>
                        </button>
                      </div>
                    </div>

                    <textarea
                      value={editorContent}
                      onChange={(e) => {
                        setEditorContent(e.target.value);
                        setIsEditorDirty(true);
                      }}
                      className="w-full h-[520px] bg-bg-secondary/90 border border-border-subtle rounded-xl p-4 font-mono text-xs text-text-primary leading-relaxed focus:outline-none focus:border-accent-cyan/50 resize-y"
                      placeholder="Markdown content..."
                      spellCheck={false}
                    />
                  </div>
                )}

                {/* ── TAB 3: Inline PDF Preview ────────────────────── */}
                {studioTab === "preview" && (
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between text-xs text-text-secondary">
                      <span>Rendered PDF preview streamed directly from the Nexus Engine.</span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setPdfPreviewKey(Date.now())}
                          className="px-2.5 py-1 rounded-md bg-bg-surface hover:bg-bg-surface/80 border border-border-subtle text-xs text-text-primary"
                        >
                          🔄 Refresh Preview
                        </button>
                        <a
                          href={getResumeFileUrl(activeDetail.path, "pdf", false)}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-md bg-bg-surface hover:bg-bg-surface/80 border border-border-subtle text-xs text-accent-cyan"
                        >
                          ↗ Open in Tab
                        </a>
                      </div>
                    </div>

                    {activeDetail.has_pdf ? (
                      <div className="w-full h-[640px] rounded-xl border border-border-subtle bg-bg-secondary overflow-hidden shadow-inner">
                        <iframe
                          key={pdfPreviewKey}
                          src={getResumeFileUrl(activeDetail.path, "pdf", false)}
                          className="w-full h-full border-none"
                          title="Rendered PDF Preview"
                        />
                      </div>
                    ) : (
                      <div className="py-24 text-center flex flex-col items-center justify-center gap-3 border border-dashed border-border-subtle rounded-xl bg-bg-surface/30">
                        <span className="text-3xl">📄</span>
                        <p className="text-sm text-text-secondary font-medium">
                          No compiled PDF artifact found yet for this document.
                        </p>
                        <button
                          onClick={() => handleRenderActiveDoc(["pdf"])}
                          disabled={rendering}
                          className="px-4 py-2 rounded-xl bg-accent-cyan/20 hover:bg-accent-cyan/30 border border-accent-cyan/40 text-accent-cyan font-medium text-xs transition-colors"
                        >
                          Compile PDF Now
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="glass-card p-16 text-center flex flex-col items-center justify-center gap-3">
                <span className="text-4xl">📄</span>
                <h3 className="text-base font-semibold text-text-primary">
                  No Document Selected
                </h3>
                <p className="text-xs text-text-muted max-w-sm">
                  Select a resume or cover letter from the portfolio list on the left to inspect its page budget, view its markdown, or compile it to PDF and Word.
                </p>
              </div>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
