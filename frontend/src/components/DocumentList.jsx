import { motion } from "framer-motion";
import { HiTrash, HiDocumentText } from "react-icons/hi2";

function DocumentList({
  uploadedFiles,
  activeDocumentId,
  onSelectDocument,
  onDeleteDocument,
  collapsed = false,
}) {
  const documents = Array.isArray(uploadedFiles) ? uploadedFiles : [];

  return (
    <div className="space-y-2">
      {documents?.length > 0 ? (
        documents.map((file) => {
        const doc = file || {};
        const isActive = activeDocumentId === doc.id;

        return (
          <motion.div
            key={doc.id}
            whileHover={{ y: -1 }}
            className={`rounded-xl border p-3 transition ${
              isActive
                ? "border-indigo-400/60 bg-indigo-500/10 shadow-[0_0_12px_rgba(99,102,241,0.2)]"
                : "border-white/10 bg-slate-950/60 hover:border-indigo-400/40"
            }`}
          >
            <button
              type="button"
              onClick={() => onSelectDocument(doc.id)}
              className="w-full text-left"
              title={doc.name}
            >
              <div className="inline-flex items-center gap-2">
                <HiDocumentText className="text-sm text-indigo-300" />
                {!collapsed && (
                  <span className="line-clamp-1 text-sm font-medium text-slate-100">{doc.name}</span>
                )}
              </div>
              {!collapsed && (
                <p className="mt-1 text-[11px] text-slate-400">
                  {doc.chunk_count || doc.chunks || "Available"} chunks
                </p>
              )}
            </button>

            {!collapsed && (
              <div className="mt-2 flex items-center justify-between">
                <span className="text-[11px] text-slate-400">{isActive ? "Active" : "Available"}</span>
                <button
                  type="button"
                  onClick={() => {}}
                  disabled
                  className="inline-flex items-center gap-1 rounded-lg border border-rose-300/20 px-2 py-1 text-[11px] font-semibold text-rose-200/60"
                >
                  <HiTrash />
                  Delete
                </button>
              </div>
            )}
          </motion.div>
        );
      })
      ) : (
        <p className="rounded-2xl border border-white/15 bg-slate-900/45 p-3 text-xs text-slate-300">
          {collapsed ? "0" : "No documents"}
        </p>
      )}
    </div>
  );
}

export default DocumentList;