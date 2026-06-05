import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import MessageBubble from "./MessageBubble";

const MotionDiv = motion.div;

function ChatBox({ messages, loading }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="glass-card scrollbar-thin flex h-full flex-col gap-3 overflow-y-auto rounded-3xl p-4 md:p-5">
      {messages.length === 0 && (
        <div className="mx-auto mt-20 max-w-md text-center">
          <p className="text-lg font-semibold text-slate-800">Ask your first question</p>
          <p className="mt-2 text-sm text-slate-500">
            Upload one or more PDFs, then start a conversation to get grounded answers with source chunks.
          </p>
        </div>
      )}

      {messages.map((msg, idx) => (
        <MessageBubble key={idx} message={msg} />
      ))}

      {loading && <div>Loading model...</div>}

      <div ref={bottomRef} />
    </div>
  );
}

export default ChatBox;
