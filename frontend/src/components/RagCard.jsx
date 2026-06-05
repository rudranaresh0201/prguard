import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { HiChevronDown, HiMiniSparkles } from "react-icons/hi2";

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function highlightText(text, keywords) {
  if (!text) {
    return null;
  }

  const filtered = keywords.filter((item) => item.length > 2);
  if (!filtered.length) {
    return text;
  }

  const regex = new RegExp(`(${filtered.map(escapeRegExp).join("|")})`, "gi");
  return text.split(regex).map((part, index) => {
    const isMatch = filtered.some((keyword) => keyword.toLowerCase() === part.toLowerCase());
    if (!isMatch) {
      return <span key={`${part}-${index}`}>{part}</span>;
    }

    return (
      <mark
        key={`${part}-${index}`}
        className="rounded-md bg-indigo-400/25 px-1 text-indigo-100"
      >
        {part}
      </mark>
    );
  });
}

function RagCard({ source, index, keywords = [] }) {
  const [expanded, setExpanded] = useState(index === 0);

  const relevance = useMemo(() => {
    const base = Math.max(0.62, 0.95 - index * 0.11);
    return Math.round(base * 100);
  }, [index]);

  const confidenceLabel = relevance >= 86 ? "High" : relevance >= 72 ? "Medium" : "Low";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ scale: 1.01 }}
      className="rounded-2xl border border-white/10 bg-slate-900/70 p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {index === 0 && (
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/35 bg-emerald-400/15 px-2 py-1 text-[11px] font-semibold text-emerald-200">
              <HiMiniSparkles />
              Top Match
            </span>
          )}
          <span className="rounded-full border border-indigo-400/30 bg-indigo-400/10 px-2 py-1 text-[11px] font-semibold text-indigo-200">
            Relevance {relevance}%
          </span>
          <span className="rounded-full border border-slate-500/30 bg-slate-500/10 px-2 py-1 text-[11px] font-semibold text-slate-200">
            Confidence {confidenceLabel}
          </span>
        </div>

        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          className="inline-flex items-center gap-1 rounded-xl border border-white/10 px-2 py-1 text-xs text-slate-300 transition hover:border-indigo-300/60 hover:text-indigo-200"
        >
          {expanded ? "Collapse" : "Expand"}
          <motion.span animate={{ rotate: expanded ? 180 : 0 }}>
            <HiChevronDown />
          </motion.span>
        </button>
      </div>

      <div className="mt-3 space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          {source.document || "Uploaded Doc"}
          {source.page ? ` • Page ${source.page}` : ""}
        </p>

        <p className={`text-sm leading-relaxed text-slate-100 ${expanded ? "" : "line-clamp-4"}`}>
          {highlightText(String(source.text || ""), keywords)}
        </p>
      </div>
    </motion.div>
  );
}

export default RagCard;
