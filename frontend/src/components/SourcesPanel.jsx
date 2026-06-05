import { motion } from "framer-motion";

const MotionDiv = motion.div;

function SourcesPanel({ sources = [] }) {
  if (!sources.length) {
    return null;
  }

  return (
    <div className="mt-3 space-y-2">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Sources</p>
      {sources.map((source, index) => (
        <MotionDiv
          key={`${source.file}-${index}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.06 }}
          className="rounded-xl border border-slate-200 bg-white p-3 transition hover:border-blue-200"
        >
          <p className="mb-1 text-[11px] font-semibold text-blue-600">{source.file}</p>
          <p className="line-clamp-4 text-xs leading-relaxed text-slate-600">{source.text}</p>
        </MotionDiv>
      ))}
    </div>
  );
}

export default SourcesPanel;
