import { useEffect, useRef, useState } from "react";
import { getKBStats, searchKB, type KBResult, type KBStats } from "../lib/api";

function DistanceBar({ distance }: { distance: number }) {
  const relevance = Math.max(0, 1 - distance);
  const pct = Math.round(relevance * 100);
  const color = pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 bg-gray-600 rounded-full h-1.5">
        <div className={`${color} h-1.5 rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 w-10 text-right">{pct}%</span>
    </div>
  );
}

export default function KBPage() {
  const [stats, setStats] = useState<KBStats | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KBResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getKBStats()
      .then(setStats)
      .catch((e) => setStatsError(e?.response?.data?.detail || "KB not available"));
  }, []);

  const handleSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setSearchError(null);
    setSearched(false);
    try {
      const res = await searchKB(q, 8);
      setResults(res.results);
      setSearched(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setSearchError(err?.response?.data?.detail || "Search failed");
    } finally {
      setSearching(false);
    }
  };

  const EXAMPLES = [
    "user authentication security",
    "performance monitoring NFR",
    "database schema design",
    "role-based access control",
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Knowledge Base</h1>
          <p className="text-sm text-gray-400 mt-1">
            Semantic search over {stats?.count ?? "…"} planning examples
          </p>
        </div>
        {stats && (
          <div className="flex items-center gap-3">
            <div className="bg-gray-700 rounded-lg px-4 py-2 text-center">
              <div className="text-xl font-bold text-blue-300">{stats.count}</div>
              <div className="text-xs text-gray-400">Documents</div>
            </div>
            <div className={`text-xs px-3 py-1 rounded-full font-medium ${
              stats.status === "ready" ? "bg-green-900 text-green-300" : "bg-yellow-900 text-yellow-300"
            }`}>
              {stats.status}
            </div>
          </div>
        )}
      </div>

      {statsError && (
        <div className="bg-yellow-900/40 border border-yellow-700 rounded-xl p-4 text-sm text-yellow-300">
          ⚠ {statsError}
          <div className="mt-2 font-mono text-xs text-yellow-400">
            Initialize with: <code>python -m src.kb.seed_cli</code>
          </div>
        </div>
      )}

      {/* Search Box */}
      <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
        <div className="flex gap-3">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Search for planning patterns, requirements, tasks…"
            className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={handleSearch}
            disabled={searching || !query.trim()}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-all"
          >
            {searching ? "…" : "Search"}
          </button>
        </div>

        {/* Quick examples */}
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => { setQuery(ex); setTimeout(handleSearch, 50); }}
              className="text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 px-3 py-1 rounded-full transition-all"
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      {searchError && (
        <p className="text-red-400 text-sm">{searchError}</p>
      )}

      {/* Results */}
      {searched && results.length === 0 && (
        <div className="text-center text-gray-400 py-8">No results found for "{query}"</div>
      )}

      {results.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs text-gray-500">{results.length} results for "{query}"</p>
          {results.map((r, i) => {
            const meta = r.metadata as Record<string, string | number>;
            return (
              <div key={i} className="bg-gray-800 rounded-xl p-5 border border-gray-700 hover:border-gray-600 transition-all">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-2">
                      <span className="text-xs bg-blue-900 text-blue-300 px-2 py-0.5 rounded-full">
                        {r.category || "general"}
                      </span>
                      {meta.domain && (
                        <span className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded-full">
                          {meta.domain}
                        </span>
                      )}
                      {meta.critic_score && (
                        <span className="text-xs bg-green-900 text-green-300 px-2 py-0.5 rounded-full">
                          critic: {Number(meta.critic_score).toFixed(2)}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-300 line-clamp-3">{r.text}</p>
                    {meta.example_tasks && (
                      <p className="text-xs text-gray-500 mt-2 line-clamp-1">
                        Tasks: {String(meta.example_tasks)}
                      </p>
                    )}
                  </div>
                  <div className="w-24 flex-shrink-0">
                    <p className="text-xs text-gray-500 mb-1 text-right">Relevance</p>
                    <DistanceBar distance={r.distance} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!searched && !searching && (
        <div className="text-center text-gray-500 py-12">
          <div className="text-4xl mb-3">🔍</div>
          <p className="text-sm">Enter a query to search the knowledge base</p>
          <p className="text-xs mt-1 text-gray-600">
            Uses semantic similarity (sentence-transformers)
          </p>
        </div>
      )}
    </div>
  );
}
