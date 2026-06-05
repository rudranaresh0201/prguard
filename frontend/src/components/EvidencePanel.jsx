import { motion } from "framer-motion";
import RagCard from "./RagCard";

function EvidencePanel({ sources = [], query = "" }) {
  const keywords = query
    .toLowerCase()
    .split(/\s+/)
    .map((word) => word.trim())
    .filter(Boolean);

  if (!sources.length) {
    return (
      <div className="rounded-2xl border border-white/10 bg-slate-900/70 p-6 text-sm text-slate-300">
        No evidence cards yet. Ask a question to inspect retrieved chunks.
      </div>
    );
  }

  return (
    <motion.div layout className="space-y-3">
      {sources.map((source, index) => (
        <RagCard
          key={`${source.document || "source"}-${source.id || index}`}
          source={source}
          index={index}
          keywords={keywords}
        />
      ))}
    </motion.div>
  );
}

export default EvidencePanel;
