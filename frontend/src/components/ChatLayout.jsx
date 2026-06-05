import { AnimatePresence, motion } from "framer-motion";
import { HiBars3 } from "react-icons/hi2";
import QueryInput from "./QueryInput";

function ChatLayout({
  started,
  query,
  onChangeQuery,
  onSubmit,
  disabled,
  loading,
  canSubmit,
  sidebar,
  sidebarCollapsed,
  mobileSidebarOpen,
  onOpenMobileSidebar,
  onCloseMobileSidebar,
  history,
  rightPanel,
}) {
  const gridColumns = sidebarCollapsed
    ? "lg:grid-cols-[72px_1fr]"
    : "lg:grid-cols-[260px_1fr]";

  return (
    <div className={`relative grid min-h-[90vh] w-full grid-cols-1 gap-4 ${gridColumns}`}>
      <button
        type="button"
        onClick={onOpenMobileSidebar}
        className="fixed left-4 top-4 z-30 inline-flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-slate-950/90 text-slate-100 transition hover:border-indigo-400/60 lg:hidden"
      >
        <HiBars3 />
      </button>

      <AnimatePresence>
        {mobileSidebarOpen && (
          <>
            <motion.button
              type="button"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={onCloseMobileSidebar}
              className="fixed inset-0 z-30 bg-slate-950/55 lg:hidden"
            />
            <motion.aside
              initial={{ x: -320 }}
              animate={{ x: 0 }}
              exit={{ x: -320 }}
              transition={{ type: "spring", stiffness: 220, damping: 28 }}
              className="fixed left-0 top-0 z-40 h-full w-[280px] border-r border-white/10 bg-[#020617] p-4 lg:hidden"
            >
              {sidebar}
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <aside className="hidden rounded-2xl border border-white/10 bg-[#020617] p-4 lg:block">
        {sidebar}
      </aside>

      <section className="flex min-h-0 flex-col">
        <div className="min-h-0 flex-1">
          <div className="scrollbar-thin h-full overflow-y-auto px-2 pb-6">
            {started ? (
              <div className="mx-auto w-full max-w-[700px] space-y-4 pb-6">{history}</div>
            ) : (
              <div className="mx-auto flex h-full min-h-[66vh] w-full max-w-[700px] flex-col">
                <div className="flex-1" />
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-8"
                >
                  <div className="space-y-3 text-center">
                    <p className="inline-block rounded-full border border-white/10 bg-white/5 px-4 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-300">
                      Document Chat
                    </p>
                    <h1 className="hero-title text-4xl font-semibold text-slate-100 md:text-5xl">
                      Ask your documents with clarity
                    </h1>
                    <p className="mx-auto max-w-2xl text-sm text-slate-400 md:text-base">
                      Clean answers, grounded in sources. Upload a PDF to get started.
                    </p>
                  </div>
                </motion.div>
                <div className="flex-1" />
              </div>
            )}
          </div>
        </div>

        {rightPanel && (
          <div className="border-t border-white/10 bg-[#020617] py-4">
            <div className="mx-auto w-full max-w-[700px]">{rightPanel}</div>
          </div>
        )}

        <div className="sticky bottom-0 w-full border-t border-white/10 bg-[#0f172a] py-4">
          <div className="mx-auto w-full max-w-[700px]">
            <QueryInput
              value={query}
              onChange={onChangeQuery}
              onSubmit={onSubmit}
              disabled={disabled}
              loading={loading}
              canSubmit={canSubmit}
            />
          </div>
        </div>
      </section>
    </div>
  );
}

export default ChatLayout;
