import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { ReportView } from "./ReportView";

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
    <div className="flex flex-1 flex-col bg-zinc-50 font-sans">
      <div className="mx-auto w-full max-w-4xl px-6 py-12">
        <div className="mb-6 flex items-center gap-4 text-sm print:hidden">
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
          <ReportView markdown={result.markdown} />
        )}
      </div>
    </div>
  );
}
