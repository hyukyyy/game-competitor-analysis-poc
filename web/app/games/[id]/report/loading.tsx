export default function Loading() {
  return (
    <div className="flex flex-1 flex-col bg-zinc-50 font-sans">
      <div className="mx-auto w-full max-w-4xl px-6 py-12">
        <div className="mb-6 flex items-center gap-4 text-sm text-zinc-400 print:hidden">
          <span>My Games</span>
          <span>/</span>
          <span>Competitors</span>
          <span>/</span>
          <span className="text-zinc-700">Report</span>
        </div>

        <div className="flex items-center gap-3 rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-200 border-t-zinc-900" />
          <span className="text-sm text-zinc-600">Loading report…</span>
        </div>

        <div className="mt-4 space-y-4 rounded-lg border border-zinc-200 bg-white p-8 shadow-sm">
          <div className="h-8 w-2/3 animate-pulse rounded bg-zinc-200" />
          <div className="h-4 w-1/3 animate-pulse rounded bg-zinc-100" />
          <div className="space-y-2 pt-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="h-3 animate-pulse rounded bg-zinc-100"
                style={{ width: `${60 + ((i * 7) % 35)}%` }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
