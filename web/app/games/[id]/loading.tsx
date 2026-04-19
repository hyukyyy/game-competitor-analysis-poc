export default function Loading() {
  return (
    <div className="flex flex-1 flex-col bg-zinc-50 font-sans">
      <div className="mx-auto w-full max-w-6xl px-6 py-12">
        <div className="text-sm text-zinc-400">&larr; My Games</div>

        <header className="mt-4 mb-8 flex items-end justify-between gap-4">
          <div className="space-y-2">
            <div className="h-8 w-64 animate-pulse rounded bg-zinc-200" />
            <div className="h-4 w-80 animate-pulse rounded bg-zinc-200" />
          </div>
          <div className="h-10 w-36 animate-pulse rounded border border-zinc-200 bg-white" />
        </header>

        <div className="flex items-center gap-3 rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-200 border-t-zinc-900" />
          <span className="text-sm text-zinc-600">Loading competitors…</span>
        </div>

        <div className="mt-4 overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
          <div className="divide-y divide-zinc-100">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-4 py-4">
                <div className="h-6 w-6 animate-pulse rounded bg-zinc-100" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 w-1/3 animate-pulse rounded bg-zinc-200" />
                  <div className="h-3 w-1/5 animate-pulse rounded bg-zinc-100" />
                </div>
                <div className="h-2 w-24 animate-pulse rounded bg-zinc-100" />
                <div className="h-2 w-24 animate-pulse rounded bg-zinc-100" />
                <div className="h-8 w-20 animate-pulse rounded bg-zinc-100" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
