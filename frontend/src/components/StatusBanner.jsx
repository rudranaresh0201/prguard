import { motion } from "framer-motion";
import { HiMiniArrowPath, HiMiniSparkles } from "react-icons/hi2";

function StatusBanner({ rebuilding, processingDoc }) {
  if (!rebuilding && !processingDoc) {
    return null;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-4 space-y-2"
    >
      {rebuilding && (
        <div className="flex items-center gap-2 rounded-2xl border border-indigo-300/30 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-100 shadow-[0_0_16px_rgba(99,102,241,0.15)]">
          <HiMiniSparkles className="text-base" />
          Rebuilding documents from storage...
        </div>
      )}

      {processingDoc && (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-300/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100 shadow-[0_0_16px_rgba(251,191,36,0.15)]">
          <HiMiniArrowPath className="animate-spin text-base" />
          Processing {processingDoc.name}
        </div>
      )}
    </motion.div>
  );
}

export default StatusBanner;
