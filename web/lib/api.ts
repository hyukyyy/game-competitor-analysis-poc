const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type Game = {
  id: number;
  platform: string;
  external_id: string;
  title: string;
  is_my_game?: boolean;
};

export type ComponentScores = {
  semantic: number;
  genre: number;
  tier: number;
  bm: number;
};

export type Competitor = {
  rank: number;
  game_id: number;
  title: string;
  platform: string;
  external_id: string;
  similarity_score: number;
  component_scores: ComponentScores;
};

export type CompetitorsResponse = {
  base_game: { id: number; platform: string; title: string };
  week_of: string;
  competitors: Competitor[];
};

export type FeedbackSignal = "upvote" | "downvote" | "clicked" | "added";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  return res.json();
}

export const api = {
  listGames: (opts: { platform?: string; mine?: boolean } = {}) => {
    const params = new URLSearchParams();
    if (opts.platform) params.set("platform", opts.platform);
    if (opts.mine) params.set("mine", "true");
    const qs = params.toString();
    return jsonFetch<Game[]>(`/games${qs ? `?${qs}` : ""}`);
  },

  getCompetitors: (baseGameId: number, limit = 10) =>
    jsonFetch<CompetitorsResponse>(
      `/competitors?base_game_id=${baseGameId}&limit=${limit}`
    ),

  getReportMarkdown: (baseGameId: number) =>
    jsonFetch<{ markdown: string }>(
      `/reports?base_game_id=${baseGameId}&format=markdown`
    ),

  postFeedback: (body: {
    base_game_id: number;
    target_game_id: number;
    week_of: string;
    signal: FeedbackSignal;
    user_id?: string;
  }) =>
    jsonFetch<{ status: string }>(`/feedback`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getFeedbackSummary: (baseGameId: number) =>
    jsonFetch<{ target_game_id: number; signal: string; n: number }[]>(
      `/feedback/summary?base_game_id=${baseGameId}`
    ),
};
