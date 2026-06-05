import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";

const MotionH1 = motion.h1;

const HEADLINES = [
  "Ask your documents anything",
  "Turn PDFs into instant answers",
  "Your personal knowledge engine",
  "Search, understand, and explore",
];

function AnimatedHeader() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setIndex((current) => (current + 1) % HEADLINES.length);
    }, 3400);

    return () => clearInterval(timer);
  }, []);

  return (
    <div className="relative overflow-hidden rounded-3xl border border-slate-200 bg-white px-6 py-5 shadow-md">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-gradient-to-r from-blue-50 via-white to-violet-50" />
      <AnimatePresence mode="wait">
        <MotionH1
          key={HEADLINES[index]}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -14 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="relative bg-gradient-to-r from-blue-600 to-violet-500 bg-clip-text text-3xl font-semibold tracking-tight text-transparent md:text-4xl"
          style={{
            fontFamily: "Space Grotesk, sans-serif",
          }}
        >
          {HEADLINES[index]}
        </MotionH1>
      </AnimatePresence>
    </div>
  );
}

export default AnimatedHeader;
