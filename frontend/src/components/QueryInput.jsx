import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { HiOutlineSparkles } from "react-icons/hi2";

const PLACEHOLDERS = [
  "Ask across all uploaded documents...",
  "Summarize the key findings from my PDFs",
  "Compare definitions and cite exact evidence",
  "What are the main risks and constraints?",
];

function QueryInput({
  value,
  onChange,
  onSubmit,
  disabled,
  hero = false,
  loading = false,
  canSubmit = true,
}) {
  const [placeholderIndex, setPlaceholderIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setPlaceholderIndex((current) => (current + 1) % PLACEHOLDERS.length);
    }, 2800);

    return () => window.clearInterval(timer);
  }, []);

  const activePlaceholder = useMemo(
    () => PLACEHOLDERS[placeholderIndex],
    [placeholderIndex]
  );

  const handleSend = () => {
    if (disabled || !canSubmit || !value.trim()) {
      return;
    }
    onSubmit();
  };

  return (
    <motion.div
      layout
      initial={hero ? { opacity: 0, y: 16 } : false}
      animate={{ opacity: 1, y: 0 }}
      className={
        hero
          ? "mx-auto w-full max-w-3xl"
          : "w-full"
      }
    >
      <div className="relative">
        <textarea
          rows={hero ? 3 : 1}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              handleSend();
            }
          }}
          placeholder=" "
          className="scrollbar-thin w-full resize-none rounded-full border border-white/10 bg-[#020617] px-5 py-3 pr-14 text-sm text-slate-100 outline-none transition focus:border-indigo-400/70 focus:ring-2 focus:ring-indigo-500/20 disabled:cursor-not-allowed disabled:opacity-60"
        />

        {!value && (
          <div className="pointer-events-none absolute left-5 top-3 text-sm text-slate-400">
            <AnimatePresence mode="wait">
              <motion.span
                key={activePlaceholder}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.35 }}
                className="inline-flex items-center gap-2"
              >
                <HiOutlineSparkles className="text-indigo-300" />
                {activePlaceholder}
              </motion.span>
            </AnimatePresence>
          </div>
        )}

        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          type="button"
          onClick={handleSend}
          disabled={disabled || !canSubmit || !value.trim()}
          className="absolute right-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition disabled:cursor-not-allowed disabled:opacity-45"
        >
          {loading ? "..." : ">"}
        </motion.button>
      </div>
    </motion.div>
  );
}

export default QueryInput;
