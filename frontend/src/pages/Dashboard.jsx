import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  HiArrowTrendingUp,
  HiCheckBadge,
  HiDocumentText,
} from "react-icons/hi2";
import AnswerPanel from "../components/AnswerPanel";
import ChatLayout from "../components/ChatLayout";
import EvidencePanel from "../components/EvidencePanel";
import Sidebar from "../components/Sidebar";
import StatusBanner from "../components/StatusBanner";
import {
  deleteDocument,
  listDocuments,
  pollTaskStatus,
  uploadPdf,
  queryRagByDocument,
  queryApi,
  resetRag,
} from "../services/api";

const TABS = ["Answer", "Evidence", "Insights"];

function normalizeDocuments(payload) {
  return (payload?.documents || []).map((doc) => ({
    id: doc.doc_id,
    name: doc.filename,
    chunks: doc.chunks,
    size: doc.size,
    uploaded_at: doc.uploaded_at,
  }));
}

function normalizeSources(sources) {
  if (!Array.isArray(sources)) {
    return [];
  }

  return sources
    .map((source, index) => ({
      id: Number(source?.id) || index + 1,
      text: String(source?.text || "").trim(),
      document: String(source?.document || source?.file || "Uploaded Doc"),
      page:
        typeof source?.page === "number"
          ? source.page
          : Number.isFinite(Number(source?.page))
          ? Number(source.page)
          : null,
    }))
    .filter((item) => item.text.length > 0);
}

function confidenceFromSources(answer, sources) {
  const quality = Math.min(100, Math.round((answer.length / 900) * 100));
  const sourceStrength = Math.min(100, sources.length * 28);
  return Math.round(0.6 * sourceStrength + 0.4 * quality);
}

function Dashboard() {
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [messages, setMessages] = useState([]);
  const [activeDocumentId, setActiveDocumentId] = useState(null);
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState("Answer");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [processingDoc, setProcessingDoc] = useState(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [querying, setQuerying] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState("");
  const [loadingMessage, setLoadingMessage] = useState("");
  const [guardWarning, setGuardWarning] = useState(false);
  const [retrievalScore, setRetrievalScore] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [statusTone, setStatusTone] = useState("neutral");
  const answerAnchorRef = useRef(null);
  const messagesEndRef = useRef(null);
  const loadingTimeoutRef = useRef(null);
  const loadingSlowRef = useRef(null);

  const inputDisabled = useMemo(() => uploading || querying, [uploading, querying]);
  const started = messages.length > 0;

  const latestAssistantMessage = useMemo(
    () => [...messages].reverse().find((item) => item.role === "assistant") || null,
    [messages]
  );

  const refreshDocuments = async () => {
    const data = await listDocuments();
    const normalized = normalizeDocuments(data);
    setUploadedFiles(normalized);
  };

  useEffect(() => {
    let mounted = true;

    const bootstrap = async () => {
      try {
        const data = await listDocuments();
        const normalized = normalizeDocuments(data);
        if (!mounted) {
          return;
        }
        setUploadedFiles(normalized);
      } catch (err) {
        if (!mounted) {
          return;
        }
        setError("Failed to load documents.");
      }
    };

    bootstrap();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => {
    if (!latestAssistantMessage) {
      return;
    }
    answerAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [latestAssistantMessage]);

  const handleUpload = async (file) => {
    setError("");
    setUploading(true);
    setUploadProgress(0);

    try {
      const data = await uploadPdf(file, () => setUploadProgress(100));

      if (data?.task_id) {
        const taskId = data.task_id;
        setProcessingDoc({ name: file.name, taskId });
        pollTaskStatus(taskId, {
          intervalMs: 2000,
          onDone: async () => {
            setProcessingDoc(null);
            await refreshDocuments();
          },
          onError: () => {
            setProcessingDoc(null);
            setError("Processing failed");
          },
        });
        return;
      }

      if (data?.doc_id || typeof data?.chunks === "number") {
        await refreshDocuments();
        setUploadProgress(100);
        return;
      }

      throw new Error("Invalid response");
    } catch {
      setError("Upload failed");
    } finally {
      setTimeout(() => {
        setUploading(false);
        setUploadProgress(0);
      }, 250);
    }
  };

  const handleDeleteFile = async (fileId) => {
    if (!fileId) return;
    setError("");
    try {
      await deleteDocument(fileId);
      await refreshDocuments();
      if (activeDocumentId === fileId) {
        setActiveDocumentId(null);
      }
    } catch {
      setError("Failed to delete document.");
    }
  };

  const handleClearAll = async () => {
    setError("");
    setClearing(true);
    try {
      await resetRag();
      setUploadedFiles([]);
      setActiveDocumentId(null);
      setMessages([]);
      setQuery("");
    } catch {
      setError("Failed to clear documents.");
    } finally {
      setClearing(false);
    }
  };

  const handleSend = async (nextQuery) => {
    if (!nextQuery.trim()) {
      return;
    }

    if (querying) {
      return;
    }

    setQuerying(true);
    setError("");
    setStatusMessage("");
    setGuardWarning(false);
    setRetrievalScore(null);
    setActiveTab("Answer");
    const ask = nextQuery.trim();
    setQuery("");

    setMessages((prev) => [...prev, { role: "user", content: ask }]);

    setLoadingMessage("Searching documents...");
    loadingTimeoutRef.current = window.setTimeout(() => {
      setLoadingMessage("Generating answer...");
    }, 1200);
    loadingSlowRef.current = window.setTimeout(() => {
      setLoadingMessage("Still working... (large response)");
    }, 5000);

    try {
      const response = activeDocumentId
        ? await queryRagByDocument(ask, activeDocumentId)
        : await queryApi(ask);

      const status = String(response?.status || "ok");
      const guardFired = Boolean(response?.guard_fired);
      const score = Number.isFinite(Number(response?.retrieval_score))
        ? Number(response.retrieval_score)
        : null;

      setGuardWarning(guardFired);
      setRetrievalScore(score);

      if (status === "busy") {
        setStatusMessage("System busy - try again in a few seconds");
        setStatusTone("warning");
      } else if (status === "timeout") {
        setStatusMessage("Request took too long - try a shorter query");
        setStatusTone("warning");
      } else if (status === "no_context") {
        setStatusMessage("No relevant info found in your documents");
        setStatusTone("neutral");
      }

      const answer = String(response?.answer || "").trim();
      const sources = normalizeSources(response?.sources);
      const confidence = score ?? confidenceFromSources(answer, sources);

      if (answer && answer.length > 0) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: answer,
            sources,
            confidence,
            query: ask,
            status,
            guardFired,
            retrievalScore: score,
          },
        ]);
      } else {
        setError("No response from model.");
      }
    } catch (err) {
      if (err?.status === 429) {
        setError("Too many requests - please wait a few seconds");
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setQuerying(false);
      setLoadingMessage("");
      if (loadingTimeoutRef.current) {
        window.clearTimeout(loadingTimeoutRef.current);
      }
      if (loadingSlowRef.current) {
        window.clearTimeout(loadingSlowRef.current);
      }
    }
  };

  const sortedFiles = useMemo(
    () => [...uploadedFiles].sort((a, b) => String(b.uploaded_at).localeCompare(String(a.uploaded_at))),
    [uploadedFiles]
  );

  const sidebar = (
    <Sidebar
      uploadedFiles={sortedFiles}
      activeDocumentId={activeDocumentId}
      uploading={uploading}
      processingDoc={processingDoc}
      uploadProgress={uploadProgress}
      onUpload={handleUpload}
      onSelectDocument={setActiveDocumentId}
      onDeleteFile={handleDeleteFile}
      onClearAll={handleClearAll}
      clearing={clearing}
      collapsed={sidebarCollapsed}
      onToggleCollapsed={() => setSidebarCollapsed((current) => !current)}
    />
  );

  const history = (
    <div className="space-y-4">
      <AnimatePresence>
        {messages.map((message, index) => {
          const isUser = message.role === "user";
          return (
            <motion.div
              key={`${message.role}-${index}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className={`rounded-2xl border p-4 shadow-sm ${
                isUser
                  ? "ml-auto max-w-[70%] border-white/10 bg-slate-800/90"
                  : "mr-auto max-w-[75%] border-white/10 bg-slate-900/90"
              }`}
            >
              <p className="mb-2 text-xs uppercase tracking-[0.18em] text-slate-400">
                {isUser ? "You" : "Assistant"}
              </p>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-100">
                {message.content}
              </p>
            </motion.div>
          );
        })}
      </AnimatePresence>

      {querying && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mr-auto max-w-[75%] rounded-2xl border border-white/10 bg-slate-900/90 p-4"
        >
          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Assistant</p>
          <div className="mt-2 flex items-center gap-2 text-sm text-slate-200">
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-300/80" />
              <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-300/50 [animation-delay:150ms]" />
              <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-300/30 [animation-delay:300ms]" />
            </span>
            <span className="text-slate-300">{loadingMessage || "Working on your request..."}</span>
          </div>
        </motion.div>
      )}
      <div ref={messagesEndRef} />
    </div>
  );

  const latestSources = latestAssistantMessage?.sources || [];
  const latestAnswer = latestAssistantMessage?.content || "";
  const latestQuery = latestAssistantMessage?.query || "";
  const latestConfidence = latestAssistantMessage?.confidence || 0;
  const latestRetrievalScore = latestAssistantMessage?.retrievalScore ?? retrievalScore ?? null;
  const latestGuardFired = latestAssistantMessage?.guardFired ?? guardWarning;

  const rightPanel = (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <div className="inline-flex rounded-full border border-white/10 bg-slate-900/70 p-1">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] transition ${
                activeTab === tab
                  ? "bg-indigo-500 text-white"
                  : "text-slate-300 hover:bg-white/10"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        <span
          className={`rounded-full border px-2 py-1 text-xs font-semibold ${
            latestRetrievalScore === null
              ? "border-white/15 bg-white/5 text-slate-200"
              : latestRetrievalScore > 0.6
              ? "border-emerald-300/30 bg-emerald-400/10 text-emerald-100"
              : latestRetrievalScore > 0.35
              ? "border-yellow-300/30 bg-yellow-400/10 text-yellow-100"
              : "border-rose-300/30 bg-rose-400/10 text-rose-100"
          }`}
        >
          {latestRetrievalScore === null
            ? `Confidence ${latestConfidence}%`
            : latestRetrievalScore > 0.6
            ? "High confidence"
            : latestRetrievalScore > 0.35
            ? "Medium confidence"
            : "Low confidence"}
        </span>
      </div>

      <div className="scrollbar-thin flex-1 overflow-y-auto">
        {activeTab === "Answer" && (
          <AnswerPanel
            answer={latestAnswer}
            query={latestQuery}
            loading={querying}
            loadingMessage={loadingMessage}
            sources={latestSources}
            guardFired={latestGuardFired}
            statusMessage={statusMessage}
            statusTone={statusTone}
            answerRef={answerAnchorRef}
          />
        )}

        {activeTab === "Evidence" && <EvidencePanel sources={latestSources} query={latestQuery} />}

        {activeTab === "Insights" && (
          <div className="space-y-3">
            <div className="rounded-2xl border border-white/10 bg-slate-900/70 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Session Overview</p>
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-white/10 bg-slate-950/60 p-3">
                  <p className="text-xs text-slate-400">Questions Asked</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-100">
                    {messages.filter((item) => item.role === "user").length}
                  </p>
                </div>
                <div className="rounded-xl border border-white/10 bg-slate-950/60 p-3">
                  <p className="text-xs text-slate-400">Evidence Cards</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-100">{latestSources.length}</p>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-900/70 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Signals</p>
              <ul className="mt-3 space-y-2 text-sm text-slate-200">
                <li className="inline-flex w-full items-center gap-2 rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2">
                  <HiDocumentText className="text-indigo-300" />
                  Active documents: {uploadedFiles.length}
                </li>
                <li className="inline-flex w-full items-center gap-2 rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2">
                  <HiCheckBadge className="text-emerald-300" />
                  Retrieval confidence: {latestConfidence}%
                </li>
                <li className="inline-flex w-full items-center gap-2 rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2">
                  <HiArrowTrendingUp className="text-purple-300" />
                  Current scope: {activeDocumentId ? "Single document" : "Cross-document"}
                </li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="relative min-h-screen bg-[#0f172a] text-slate-100">
      <div className="mx-auto max-w-[1400px] p-4 md:p-6">
        <StatusBanner rebuilding={rebuilding} processingDoc={processingDoc} />
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-4 rounded-2xl border border-rose-300/35 bg-rose-500/10 px-4 py-3 text-sm text-rose-100 shadow-[0_0_20px_rgba(244,63,94,0.15)]"
          >
            {error}
          </motion.div>
        )}

        {!uploadedFiles.length && !started && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-4 rounded-2xl border border-white/10 bg-slate-900/70 px-4 py-3 text-sm text-slate-200"
          >
            No documents uploaded yet
            <br />
            Upload a PDF to get started
          </motion.div>
        )}

        <ChatLayout
          started={started}
          query={query}
          onChangeQuery={setQuery}
          onSubmit={() => handleSend(query)}
          disabled={inputDisabled}
          loading={querying}
          canSubmit={uploadedFiles.length > 0}
          sidebar={sidebar}
          sidebarCollapsed={sidebarCollapsed}
          mobileSidebarOpen={mobileSidebarOpen}
          onOpenMobileSidebar={() => setMobileSidebarOpen(true)}
          onCloseMobileSidebar={() => setMobileSidebarOpen(false)}
          history={history}
          rightPanel={rightPanel}
        />
      </div>
    </div>
  );
}

export default Dashboard;
