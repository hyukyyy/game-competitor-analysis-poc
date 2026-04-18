"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

export function AddMyGameForm() {
  const router = useRouter();
  const [platform, setPlatform] = useState("steam");
  const [appid, setAppid] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(
    null,
  );

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!appid.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      const game = await api.addMyGame({ platform, appid: appid.trim() });
      setMsg({
        kind: "ok",
        text: `Registered: ${game.title ?? "(untitled)"} (#${game.id})`,
      });
      setAppid("");
      router.refresh();
    } catch (e) {
      setMsg({ kind: "err", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-8 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
      <h2 className="mb-1 text-sm font-semibold text-zinc-900">
        Register a new game
      </h2>
      <p className="mb-4 text-xs text-zinc-500">
        Enter a Steam appid (e.g. <span className="font-mono">1063730</span> for
        New World: Aeternum). The game will be fetched from Steam, normalized,
        and flagged as your analysis target.
      </p>
      <form
        onSubmit={onSubmit}
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
      >
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-zinc-600">Platform</span>
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            className="rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none"
          >
            <option value="steam">Steam</option>
          </select>
        </label>
        <label className="flex flex-1 flex-col gap-1">
          <span className="text-xs font-medium text-zinc-600">AppID</span>
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            placeholder="e.g. 1063730"
            value={appid}
            onChange={(e) => setAppid(e.target.value)}
            className="rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none"
          />
        </label>
        <button
          type="submit"
          disabled={busy || !appid.trim()}
          className="rounded bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:bg-zinc-400"
        >
          {busy ? "Registering…" : "Register"}
        </button>
      </form>
      {msg && (
        <p
          className={`mt-3 text-xs ${msg.kind === "ok" ? "text-emerald-700" : "text-rose-700"}`}
        >
          {msg.text}
        </p>
      )}
    </div>
  );
}
