import Link from "next/link";
import { notFound } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const baseGameId = Number(id);
  if (!Number.isFinite(baseGameId)) notFound();

  const result = await api
    .getReportMarkdown(baseGameId)
    .catch((e: Error) => ({ error: e.message }) as const);

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-12">
      <div className="mb-6 flex items-center gap-4 text-sm">
        <Link href="/" className="text-zinc-600 hover:underline">
          My Games
        </Link>
        <span className="text-zinc-400">/</span>
        <Link
          href={`/games/${baseGameId}`}
          className="text-zinc-600 hover:underline"
        >
          Competitors
        </Link>
        <span className="text-zinc-400">/</span>
        <span className="text-zinc-900">Report</span>
      </div>

      {"error" in result ? (
        <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-12 text-center">
          <h1 className="text-lg font-semibold text-zinc-900">
            Report unavailable
          </h1>
          <p className="mt-2 text-sm text-zinc-600">{result.error}</p>
          <p className="mt-4 text-xs text-zinc-500">
            Generate via{" "}
            <code className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono">
              gca report --game-id {baseGameId}
            </code>
          </p>
        </div>
      ) : (
        <article className="markdown-body rounded-lg border border-zinc-200 bg-white p-8 shadow-sm">
          <ReactMarkdown
            components={{
              h1: (props) => (
                <h1 className="mb-2 text-2xl font-semibold text-zinc-900" {...props} />
              ),
              h2: (props) => (
                <h2 className="mt-8 mb-3 text-xl font-semibold text-zinc-900" {...props} />
              ),
              h3: (props) => (
                <h3 className="mt-6 mb-2 text-lg font-semibold text-zinc-900" {...props} />
              ),
              p: (props) => (
                <p className="my-3 leading-relaxed text-zinc-700" {...props} />
              ),
              ul: (props) => (
                <ul className="my-3 list-disc pl-6 text-zinc-700" {...props} />
              ),
              ol: (props) => (
                <ol className="my-3 list-decimal pl-6 text-zinc-700" {...props} />
              ),
              li: (props) => <li className="my-1" {...props} />,
              hr: () => <hr className="my-6 border-zinc-200" />,
              strong: (props) => (
                <strong className="font-semibold text-zinc-900" {...props} />
              ),
              em: (props) => (
                <em className="italic text-zinc-600" {...props} />
              ),
              code: (props) => (
                <code
                  className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs text-zinc-800"
                  {...props}
                />
              ),
              table: (props) => (
                <div className="my-4 overflow-x-auto">
                  <table className="w-full border-collapse text-sm" {...props} />
                </div>
              ),
              thead: (props) => <thead className="bg-zinc-50" {...props} />,
              th: (props) => (
                <th
                  className="border-b border-zinc-200 px-3 py-2 text-left font-semibold text-zinc-900"
                  {...props}
                />
              ),
              td: (props) => (
                <td className="border-b border-zinc-100 px-3 py-2 text-zinc-700" {...props} />
              ),
            }}
          >
            {result.markdown}
          </ReactMarkdown>
        </article>
      )}
    </div>
  );
}
