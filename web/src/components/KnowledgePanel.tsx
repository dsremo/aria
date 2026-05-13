import { useState } from 'react'

interface Hit {
  id?: string
  citation?: string
  title?: string
  body?: string
  excerpt?: string
  score?: number
  relevance?: number
  [key: string]: any
}

function SearchSection({ label, endpoint, placeholder }: {
  label: string; endpoint: string; placeholder: string
}) {
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<Hit[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [searched, setSearched] = useState(false)

  async function search() {
    if (!query.trim()) return
    setLoading(true); setError(''); setHits([]); setSearched(true)
    try {
      const r = await fetch(endpoint, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({query, limit: 10})
      })
      const d = await r.json()
      if (!d.ok) { setError(d.error || 'Search failed'); return }
      setHits(d.hits || [])
    } catch(e: any) { setError(e.message) }
    finally { setLoading(false) }
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') search()
  }

  return (
    <div className="mb-8">
      <h3 className="text-ui-accent font-semibold mb-2">{label}</h3>
      <div className="flex gap-2 mb-3">
        <input
          value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={onKey}
          placeholder={placeholder}
          className="flex-1 bg-ui-bg-2 text-ui-text border border-ui-border rounded px-2.5 py-1.5 font-mono focus:outline-none focus:border-ui-accent"
        />
        <button onClick={search} disabled={loading}
          className="px-4 py-1.5 rounded border border-ui-accent bg-ui-accent/15 text-ui-text hover:bg-ui-accent/25 font-bold min-w-20 disabled:opacity-50 transition-colors">
          {loading ? '…' : 'Search'}
        </button>
      </div>
      {error && <div className="text-sev-crit text-[0.85rem] mb-2">⚠ {error}</div>}
      {searched && !loading && hits.length === 0 && !error && (
        <div className="text-ui-text-faint text-[0.85rem]">No results for "{query}". Try a broader term.</div>
      )}
      {hits.map((h, i) => {
        const scoreDisplay = h.score ?? h.relevance
        const scoreText = typeof scoreDisplay === 'number' ? scoreDisplay.toFixed(3) : scoreDisplay
        return (
          <div key={i} className="bg-ui-bg-1/60 border border-ui-border rounded-md p-3 mb-2">
            <div className="flex justify-between mb-1">
              <span className="font-bold text-ui-text text-[0.9rem]">
                {h.title || h.id || `Result ${i+1}`}
              </span>
              {scoreDisplay != null && (
                <span className="text-sev-ok text-[0.78rem]">score: {scoreText}</span>
              )}
            </div>
            {h.citation && (
              <div className="text-sev-warn text-[0.75rem] mb-1">📚 {h.citation}</div>
            )}
            <div className="text-ui-text-dim text-[0.82rem] leading-relaxed">
              {h.excerpt || h.body || '(no excerpt)'}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function KnowledgePanel() {
  return (
    <div className="p-4 font-mono max-w-[900px]">
      <h2 className="mb-1 text-ui-text font-bold">Knowledge Base</h2>
      <p className="text-ui-text-faint text-[0.85rem] mb-6">
        279 doctrine entries · 2,178 lessons learned — full-text search
      </p>
      <SearchSection
        label="Doctrine Search"
        endpoint="/api/doctrine/search"
        placeholder="e.g. cryo tank, ECSS structural, EMU water…"
      />
      <SearchSection
        label="Lessons Learned Search"
        endpoint="/api/lessons/search"
        placeholder="e.g. Apollo 13, ammonia leak, BCDU, hayabusa…"
      />
    </div>
  )
}
