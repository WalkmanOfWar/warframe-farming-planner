import React, { useState } from 'react'

const API = '/api/route'

function lines(text) {
  return text.split('\n').map((s) => s.trim()).filter(Boolean)
}

export default function App() {
  const [accountId, setAccountId] = useState('')
  const [nonce, setNonce] = useState('')
  const [wishlist, setWishlist] = useState('')
  const [inventory, setInventory] = useState(null)
  const [invName, setInvName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  async function onInventory(e) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      setInventory(JSON.parse(await file.text()))
      setInvName(file.name)
      setError('')
    } catch {
      setInventory(null)
      setInvName('')
      setError(`${file.name} is not valid JSON.`)
    }
  }

  async function plan() {
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const body = {
        account_id: accountId.trim() || null,
        nonce: nonce.trim() || null,
        wishlist: wishlist.trim() ? lines(wishlist) : null,
        inventory,
      }
      const res = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Request failed')
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="wrap">
      <header>
        <h1>Warframe Farming Planner</h1>
        <p className="sub">
          Plan the fewest missions to farm everything you're still missing.
        </p>
      </header>

      <section className="card">
        <label>
          Account ID <span className="hint">(24-hex, not username)</span>
          <input
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            placeholder="e.g. 692f1267db467ef12005e8f7"
          />
        </label>

        <label>
          Nonce <span className="hint">(optional — full inventory incl. loose parts)</span>
          <input
            value={nonce}
            onChange={(e) => setNonce(e.target.value)}
            placeholder="from warframe-api-helper, with the game running"
          />
        </label>

        <label>
          Inventory file <span className="hint">(optional — inventory.json export)</span>
          <input type="file" accept="application/json,.json" onChange={onInventory} />
          {invName && <span className="ok">loaded {invName}</span>}
        </label>

        <label>
          Wishlist <span className="hint">(optional — one item per line; empty = everything)</span>
          <textarea
            rows={3}
            value={wishlist}
            onChange={(e) => setWishlist(e.target.value)}
            placeholder={'Caliban Prime\nVolt Prime'}
          />
        </label>

        <button onClick={plan} disabled={loading}>
          {loading ? 'Planning…' : 'Plan route'}
        </button>
        {error && <p className="error">{error}</p>}
      </section>

      {result && <Results r={result} />}

      <footer>
        Unofficial fan tool. Data from WFCD / warframestat. Not affiliated with
        Digital Extremes.
      </footer>
    </div>
  )
}

function Results({ r }) {
  if (!r.missing_equipment) {
    return <section className="card"><p>Nothing to farm — you own everything in the target set. 🎉</p></section>
  }
  const primeCount = r.prime.length
  const nonPrimeParts = r.non_prime.reduce((n, m) => n + m.parts.length, 0)
  return (
    <>
      <section className="summary">
        <Stat n={r.missing_equipment} label="missing items" />
        <Stat n={nonPrimeParts} label="non-prime parts" />
        <Stat n={primeCount} label="prime parts" />
        <Stat n={r.vaulted_part_count} label="vaulted parts" />
      </section>

      {r.non_prime.length > 0 && (
        <section className="card">
          <h2>Non-Prime — {r.non_prime.length} mission(s)</h2>
          {r.non_prime.map((m, i) => (
            <div key={i} className="mission">
              <div className="node">{i + 1}. {m.node} <span className="mode">{m.game_mode}</span></div>
              <ul>{m.parts.map((p) => <li key={p}>{p}</li>)}</ul>
            </div>
          ))}
        </section>
      )}

      {r.prime.length > 0 && (
        <section className="card">
          <h2>Prime — {primeCount} part(s)</h2>
          <p className="note">You farm a relic's <b>tier</b>, then crack it at a void fissure.</p>
          <table className="prime">
            <thead><tr><th>Part</th><th>In-rotation relics</th></tr></thead>
            <tbody>
              {r.prime.map((p) => (
                <tr key={p.part}>
                  <td>{p.part}</td>
                  <td>
                    {p.relics.map((rel) => <span key={rel} className="relic">{rel}</span>)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {r.tiers.length > 0 && (
            <div className="tiers">
              <h3>Relic tiers to farm</h3>
              {r.tiers.map((t) => (
                <div key={t.tier} className="tier">
                  <span className={`badge t-${t.tier.toLowerCase()}`}>{t.tier}</span>
                  <span>{t.where}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {r.vaulted_equipment.length > 0 && (
        <Collapsible title={`Vaulted / not farmable now (${r.vaulted_equipment.length})`}>
          <ul className="cols">{r.vaulted_equipment.map((x) => <li key={x}>{x}</li>)}</ul>
        </Collapsible>
      )}

      {r.no_mission_source.length > 0 && (
        <Collapsible title={`Not from mission drops — market / clan / syndicate / lich / Baro / quest (${r.no_mission_source.length})`}>
          <ul className="cols">{r.no_mission_source.map((x) => <li key={x}>{x}</li>)}</ul>
        </Collapsible>
      )}
    </>
  )
}

function Stat({ n, label }) {
  return <div className="stat"><div className="num">{n}</div><div className="lbl">{label}</div></div>
}

function Collapsible({ title, children }) {
  const [open, setOpen] = useState(false)
  return (
    <section className="card">
      <button className="collapse" onClick={() => setOpen(!open)}>
        {open ? '▾' : '▸'} {title}
      </button>
      {open && <div className="collapse-body">{children}</div>}
    </section>
  )
}
