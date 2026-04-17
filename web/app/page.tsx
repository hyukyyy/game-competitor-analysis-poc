import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const games = await api.listGames({ mine: true }).catch(() => []);

  return (
    <div className="flex flex-col flex-1 bg-zinc-50 font-sans">
      <main className="mx-auto w-full max-w-5xl px-6 py-12">
        <header className="mb-8 flex items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">
              My Games
            </h1>
            <p className="mt-1 text-sm text-zinc-600">
              PM-registered titles tracked for competitor analysis.
            </p>
          </div>
          <span className="rounded-full bg-zinc-900 px-3 py-1 text-xs font-medium text-white">
            {games.length} game{games.length === 1 ? "" : "s"}
          </span>
        </header>

        {games.length === 0 ? (
          <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-12 text-center">
            <p className="text-sm text-zinc-600">
              No games registered yet. Run{" "}
              <code className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs">
                gca add-my-game --platform steam --appid &lt;id&gt;
              </code>{" "}
              to register one.
            </p>
          </div>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {games.map((g) => (
              <li
                key={g.id}
                className="flex flex-col rounded-lg border border-zinc-200 bg-white p-5 shadow-sm transition hover:shadow"
              >
                <div className="mb-3 flex items-center justify-between text-xs">
                  <span className="rounded bg-zinc-100 px-2 py-0.5 font-mono text-zinc-600">
                    {g.platform}
                  </span>
                  <span className="font-mono text-zinc-400">#{g.id}</span>
                </div>
                <h2 className="mb-1 line-clamp-2 text-lg font-semibold text-zinc-900">
                  {g.title ?? "(untitled)"}
                </h2>
                <p className="mb-4 font-mono text-xs text-zinc-500">
                  {g.external_id}
                </p>
                <div className="mt-auto flex gap-2">
                  <Link
                    href={`/games/${g.id}`}
                    className="flex-1 rounded bg-zinc-900 px-3 py-2 text-center text-sm font-medium text-white transition hover:bg-zinc-700"
                  >
                    Competitors
                  </Link>
                  <Link
                    href={`/games/${g.id}/report`}
                    className="flex-1 rounded border border-zinc-300 bg-white px-3 py-2 text-center text-sm font-medium text-zinc-900 transition hover:bg-zinc-100"
                  >
                    Report
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
