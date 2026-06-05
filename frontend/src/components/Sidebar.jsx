import { motion } from "framer-motion";
import {
  HiBars3BottomLeft,
  HiFolder,
  HiSquares2X2,
  HiChatBubbleOvalLeftEllipsis,
  HiMiniSparkles,
} from "react-icons/hi2";
import DocumentList from "./DocumentList";
import FileUpload from "./FileUpload";

const NAV_ITEMS = [
  { icon: HiFolder, label: "Documents", active: true },
  { icon: HiSquares2X2, label: "Collections", active: false },
  { icon: HiChatBubbleOvalLeftEllipsis, label: "Sessions", active: false },
];

function Sidebar({
  uploadedFiles,
  activeDocumentId,
  uploading,
  processingDoc,
  uploadProgress,
  onUpload,
  onSelectDocument,
  onDeleteFile,
  onClearAll,
  clearing,
  collapsed = false,
  onToggleCollapsed,
}) {
  return (
    <div className="flex h-full min-h-[600px] flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          {!collapsed && (
            <div className="flex items-center gap-2">
              <HiMiniSparkles className="text-indigo-300" />
              <h2 className="text-lg font-semibold text-slate-100">Documents</h2>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={onToggleCollapsed}
          className="rounded-lg border border-white/10 bg-slate-950/70 p-2 text-slate-300 transition hover:border-indigo-400/50 hover:text-indigo-200"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <motion.span animate={{ rotate: collapsed ? 180 : 0 }} className="block">
            <HiBars3BottomLeft />
          </motion.span>
        </button>
      </div>

      {!collapsed && (
        <nav className="space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.label}
                type="button"
                className={`inline-flex w-full items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] transition ${
                  item.active
                    ? "border border-indigo-300/35 bg-indigo-500/10 text-indigo-100"
                    : "text-slate-400 hover:bg-white/5"
                }`}
              >
                <Icon className="text-base" />
                {item.label}
              </button>
            );
          })}
        </nav>
      )}

      <FileUpload
        onUpload={onUpload}
        uploading={uploading}
        processingDoc={processingDoc}
        uploadProgress={uploadProgress}
        collapsed={collapsed}
      />

      <div className="scrollbar-thin flex-1 overflow-y-auto pr-1">
        <DocumentList
          uploadedFiles={uploadedFiles}
          activeDocumentId={activeDocumentId}
          onSelectDocument={onSelectDocument}
          onDeleteDocument={onDeleteFile}
          collapsed={collapsed}
        />
      </div>

      <div className="space-y-2">
        <button
          type="button"
          onClick={() => onSelectDocument(null)}
          className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs font-semibold uppercase tracking-[0.13em] text-slate-200 transition hover:border-indigo-400/50"
          title="Search across all documents"
        >
          {collapsed ? "All" : "Search All Docs"}
        </button>

        <button
          type="button"
          onClick={onClearAll}
          disabled={clearing || uploading || Boolean(processingDoc) || uploadedFiles.length === 0}
          className="w-full rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.13em] text-rose-100 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-50"
          title="Clear all documents"
        >
          {clearing ? "Clearing..." : collapsed ? "Clear" : "Clear All"}
        </button>
      </div>
    </div>
  );
}

export default Sidebar;
