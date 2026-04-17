import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { CompetitorsTable } from "./CompetitorsTable";

export const dynamic = "force-dynamic";

export default async function GameCompetitorsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const baseGameId = Number(id);
  if (!Number.isFinite(baseGameId)) notFound();

  const data = await api.getCompetitors(baseGameId, 10).catch((e: Error) => {
    if (e.message.includes("404")) return null;
    throw e;
  });

  if (!data) {
    return (
      <div className="mx-auto w-full max-w-5xl px-6 py-12">
        <Link href="/" className="text-sm text-zinc-600 hover:underline">
          &larr; My Games
        </Link>
        <div className="mt-8 rounded-lg border border-dashed border-zinc-300 bg-white p-12 text-center">
          <h1 className="text-lg font-semibold text-zinc-900">
            No similarity data yet
          </h1>
          <p className="mt-2 text-sm text-zinc-600">
            Run{" "}
            <code className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs">
              gca similarity
            </code>{" "}
            to compute competitors for this game.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-12">
      <Link href="/" className="text-sm text-zinc-600 hover:underline">
        &larr; My Games
      </Link>

      <header className="mt-4 mb-8 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">
            {data.base_game.title}
          </h1>
          <p className="mt-1 text-sm text-zinc-600">
            Top competitors · week of{" "}
            <span className="font-mono">{data.week_of}</span> ·{" "}
            <span className="font-mono">{data.base_game.platform}</span>
          </p>
        </div>
        <Link
          href={`/games/${baseGameId}/report`}
          className="rounded border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-900 transition hover:bg-zinc-100"
        >
          Weekly Report &rarr;
        </Link>
      </header>

      <CompetitorsTable
        baseGameId={baseGameId}
        weekOf={data.week_of}
        competitors={data.competitors}
      />
    </div>
  );
}
