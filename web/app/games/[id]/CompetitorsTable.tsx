"use client";

import { useState } from "react";
import { api, storeUrl, type Competitor, type FeedbackSignal } from "@/lib/api";

type FeedbackState = Record<number, { signal: FeedbackSignal; ts: number }>;

function Bar({ value, color }: { value: number; color: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-zinc-100">
        <div
          className={`h-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-xs tabular-nums text-zinc-600">
        {value.toFixed(2)}
      </span>
    </div>
  );
}

export function CompetitorsTable({
  baseGameId,
  weekOf,
  competitors,
}: {
  baseGameId: number;
  weekOf: string;
  competitors: Competitor[];
}) {
  const [feedback, setFeedback] = useState<FeedbackState>({});
  const [toast, setToast] = useState<string | null>(null);

  async function vote(targetGameId: number, signal: FeedbackSignal) {
    try {
      await api.postFeedback({
        base_game_id: baseGameId,
        target_game_id: targetGameId,
        week_of: weekOf,
        signal,
      });
      setFeedback((prev) => ({
        ...prev,
        [targetGameId]: { signal, ts: Date.now() },
      }));
      setToast(`${signal} recorded`);
      setTimeout(() => setToast(null), 1500);
    } catch (e) {
      setToast(`failed: ${(e as Error).message}`);
      setTimeout(() => setToast(null), 3000);
    }
  }

  return (
    <>
      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 text-left text-xs font-medium uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-4 py-3 w-12">#</th>
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3 w-24">Score</th>
              <th className="px-4 py-3">Semantic</th>
              <th className="px-4 py-3">Genre</th>
              <th className="px-4 py-3">Tier</th>
              <th className="px-4 py-3">BM</th>
              <th className="px-4 py-3 w-32 text-center">Feedback</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {competitors.map((c) => {
              const fb = feedback[c.game_id];
              return (
                <tr key={c.game_id} className="hover:bg-zinc-50">
                  <td className="px-4 py-3 font-mono text-zinc-500">
                    {c.rank}
                  </td>
                  <td className="px-4 py-3">
                    {(() => {
                      const url = storeUrl(c.platform, c.external_id);
                      const inner = (
                        <>
                          <div className="font-medium text-zinc-900 group-hover:text-indigo-600 group-hover:underline">
                            {c.title}
                          </div>
                          <div className="font-mono text-xs text-zinc-500">
                            {c.platform} · {c.external_id}
                          </div>
                        </>
                      );
                      return url ? (
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="group block"
                        >
                          {inner}
                        </a>
                      ) : (
                        inner
                      );
                    })()}
                  </td>
                  <td className="px-4 py-3 font-mono text-sm font-semibold tabular-nums text-zinc-900">
                    {c.similarity_score.toFixed(3)}
                  </td>
                  <td className="px-4 py-3">
                    <Bar
                      value={c.component_scores.semantic}
                      color="bg-indigo-500"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <Bar
                      value={c.component_scores.genre}
                      color="bg-emerald-500"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <Bar
                      value={c.component_scores.tier}
                      color="bg-amber-500"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <Bar value={c.component_scores.bm} color="bg-rose-500" />
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex justify-center gap-1">
                      <button
                        onClick={() => vote(c.game_id, "upvote")}
                        aria-label="upvote"
                        className={`rounded px-2 py-1 text-xs transition ${
                          fb?.signal === "upvote"
                            ? "bg-emerald-600 text-white"
                            : "bg-zinc-100 text-zinc-700 hover:bg-emerald-100"
                        }`}
                      >
                        ▲
                      </button>
                      <button
                        onClick={() => vote(c.game_id, "downvote")}
                        aria-label="downvote"
                        className={`rounded px-2 py-1 text-xs transition ${
                          fb?.signal === "downvote"
                            ? "bg-rose-600 text-white"
                            : "bg-zinc-100 text-zinc-700 hover:bg-rose-100"
                        }`}
                      >
                        ▼
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {toast && (
        <div className="fixed bottom-6 right-6 rounded-md bg-zinc-900 px-4 py-2 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}
    </>
  );
}
