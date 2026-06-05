export default function MessageBubble({ message }) {
  const text = message?.content || message?.text || "";

  const sources = Array.isArray(message?.sources)
    ? message.sources
        .map((src, idx) => {
          if (src && typeof src === "object") {
            return {
              id: Number(src.id) || idx + 1,
              document: src.document || src.title || "Uploaded Doc",
              page: src.page ?? null,
              text: String(src.text || "").trim(),
            };
          }

          if (typeof src === "string") {
            return {
              id: idx + 1,
              document: "Uploaded Doc",
              page: null,
              text: src,
            };
          }

          return null;
        })
        .filter(Boolean)
    : [];

  const scrollToSource = (sourceId) => {
    const el = document.getElementById(`source-${sourceId}`);
    if (!el) {
      return;
    }

    el.scrollIntoView({ behavior: "smooth", block: "center" });
    const originalBackground = el.style.background;
    el.style.background = "#e0f2fe";
    window.setTimeout(() => {
      el.style.background = originalBackground;
    }, 900);
  };

  const renderTextWithCitations = (value) => {
    if (!value) {
      return null;
    }

    const parts = String(value).split(/(\[\d+\])/g);
    return parts.map((part, idx) => {
      const match = part.match(/^\[(\d+)\]$/);
      if (!match) {
        return <span key={idx}>{part}</span>;
      }

      const citationId = Number(match[1]);
      return (
        <span
          key={idx}
          className="citation"
          onClick={() => scrollToSource(citationId)}
        >
          {part}
        </span>
      );
    });
  };

  return (
    <div>
      <div className="text-content whitespace-pre-wrap">{renderTextWithCitations(text)}</div>
      {sources.length > 0 && (
        <div className="mt-4">
          <div className="font-semibold text-sm mb-2">Sources</div>

          <div className="grid gap-2">
            {sources.map((src) => (
              <div
                id={`source-${src.id}`}
                key={src.id}
                className="source-card"
              >
                <div className="source-title">
                  [{src.id}] {src.document}
                  {src.page ? ` • Page ${src.page}` : ""}
                </div>

                <div className="source-text">{src.text}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <style>{`
        .source-card {
          border-left: 3px solid #3b82f6;
          padding: 8px;
          margin-bottom: 8px;
          background: #f9fafb;
          border-radius: 6px;
          transition: background-color 0.25s ease;
        }

        .source-title {
          font-size: 12px;
          color: #374151;
          margin-bottom: 4px;
          font-weight: 600;
        }

        .source-text {
          font-size: 14px;
          color: #4b5563;
        }

        .citation {
          color: #2563eb;
          cursor: pointer;
          font-weight: 500;
        }

        .citation:hover {
          text-decoration: underline;
        }
      `}</style>
    </div>
  );
}
