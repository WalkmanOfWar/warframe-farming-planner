import React, { useRef, useState } from 'react'
import {
  AlertCircle, CheckCircle2, ChevronDown, ChevronRight,
  Crosshair, Gem, Loader2, Lock, MapPin, ShoppingBag,
  Swords, Upload, X,
} from 'lucide-react'

const API = '/api/route'

const C = {
  bg:          '#090d12',
  surface:     '#0f1923',
  surface2:    '#182030',
  border:      '#2a3a4a',
  gold:        '#d4b35a',
  goldDim:     '#a8893e',
  goldFaint:   'rgba(212,179,90,0.08)',
  goldBorder:  'rgba(212,179,90,0.3)',
  accent:      '#4aa3df',
  accentFaint: 'rgba(74,163,223,0.12)',
  accentBorder:'rgba(74,163,223,0.3)',
  text:        '#e6edf3',
  muted:       '#7a8a9a',
  error:       '#f85149',
  errorFaint:  'rgba(248,81,73,0.08)',
  errorBorder: 'rgba(248,81,73,0.3)',
  success:     '#3fb950',
  successFaint:'rgba(63,185,80,0.08)',
  successBorder:'rgba(63,185,80,0.3)',
  lith:        '#2d5c35',
  meso:        '#3a3a7a',
  neo:         '#5a3a7a',
  axi:         '#7a5a2a',
  requiem:     '#5a2a2a',
}

const TIER_COLOR = { Lith: C.lith, Meso: C.meso, Neo: C.neo, Axi: C.axi, Requiem: C.requiem }

function lines(text) {
  return text.split('\n').map((s) => s.trim()).filter(Boolean)
}

/* ── Primitives ───────────────────────────────────────────── */

function Card({ children, accent = false, style = {} }) {
  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${accent ? C.goldBorder : C.border}`,
      borderTop: accent ? `2px solid ${C.gold}` : `1px solid ${C.border}`,
      borderRadius: 14,
      boxShadow: '0 4px 24px rgba(0,0,0,0.4)',
      ...style,
    }}>
      {children}
    </div>
  )
}

function Btn({ children, onClick, disabled, fullWidth = false, variant = 'gold' }) {
  const [hov, setHov] = useState(false)
  const base = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    gap: 8, border: 'none', borderRadius: 10, fontWeight: 700,
    fontSize: 15, cursor: disabled ? 'default' : 'pointer',
    padding: '12px 20px', transition: 'opacity .15s',
    opacity: disabled ? 0.5 : hov ? 0.88 : 1,
    width: fullWidth ? '100%' : undefined,
  }
  const colors = variant === 'gold'
    ? { background: C.gold, color: '#111' }
    : { background: 'transparent', border: `1px solid ${C.border}`, color: C.text }
  return (
    <button
      onClick={onClick} disabled={disabled}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{ ...base, ...colors }}
    >
      {children}
    </button>
  )
}

function TextInput({ value, onChange, placeholder }) {
  const [focus, setFocus] = useState(false)
  return (
    <input
      value={value} onChange={onChange} placeholder={placeholder}
      spellCheck={false}
      onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
      style={{
        width: '100%', background: C.bg, color: C.text,
        border: `1px solid ${focus ? C.accent : C.border}`,
        borderRadius: 8, padding: '10px 12px', fontSize: 14,
        outline: 'none', boxSizing: 'border-box',
        transition: 'border-color .15s',
      }}
    />
  )
}

function TextArea({ value, onChange, placeholder, rows = 3 }) {
  const [focus, setFocus] = useState(false)
  return (
    <textarea
      value={value} onChange={onChange} placeholder={placeholder} rows={rows}
      onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
      style={{
        width: '100%', background: C.bg, color: C.text,
        border: `1px solid ${focus ? C.accent : C.border}`,
        borderRadius: 8, padding: '10px 12px', fontSize: 14,
        outline: 'none', boxSizing: 'border-box', resize: 'vertical',
        fontFamily: 'inherit', transition: 'border-color .15s',
      }}
    />
  )
}

function FieldLabel({ label, hint }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
      <span style={{ fontWeight: 600, fontSize: 14, color: C.text }}>{label}</span>
      {hint && <span style={{ fontSize: 12, color: C.muted }}>{hint}</span>}
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <FieldLabel label={label} hint={hint} />
      {children}
    </div>
  )
}

function Badge({ children, color, bg }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      background: bg || C.surface2,
      color: color || C.muted,
      border: `1px solid ${C.border}`,
      borderRadius: 6, padding: '2px 8px',
      fontSize: 12, fontWeight: 600,
    }}>
      {children}
    </span>
  )
}

function TierBadge({ tier }) {
  const bg = TIER_COLOR[tier] || C.surface2
  return (
    <span style={{
      display: 'inline-block', minWidth: 64, textAlign: 'center',
      background: bg, color: '#fff',
      borderRadius: 6, padding: '2px 10px',
      fontSize: 12, fontWeight: 700,
    }}>
      {tier}
    </span>
  )
}

/* ── Main App ─────────────────────────────────────────────── */

export default function App() {
  const [accountId, setAccountId] = useState('')
  const [nonce, setNonce] = useState('')
  const [wishlist, setWishlist] = useState('')
  const [inventory, setInventory] = useState(null)
  const [invName, setInvName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const fileRef = useRef(null)

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

  function clearInventory() {
    setInventory(null)
    setInvName('')
    if (fileRef.current) fileRef.current.value = ''
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
    <div style={{ background: C.bg, minHeight: '100vh', color: C.text, fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      <div style={{ maxWidth: 680, margin: '0 auto', padding: '48px 20px 80px' }}>

        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 56, height: 56, borderRadius: 16, marginBottom: 16,
            background: C.goldFaint, border: `1px solid ${C.goldBorder}`,
          }}>
            <Swords size={26} color={C.gold} />
          </div>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 800, color: C.gold, letterSpacing: '.3px' }}>
            Warframe Farming Planner
          </h1>
          <p style={{ margin: '8px 0 0', fontSize: 14, color: C.muted }}>
            Plan the fewest missions to farm everything you're still missing.
          </p>
        </div>

        {/* Form card */}
        <Card accent style={{ marginBottom: 24, padding: 28 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24 }}>
            <Crosshair size={16} color={C.gold} />
            <span style={{ fontWeight: 700, fontSize: 16, color: C.gold }}>Your profile</span>
          </div>

          <Field label="Account ID" hint="24-hex gid cookie, not username">
            <TextInput value={accountId} onChange={e => setAccountId(e.target.value)}
              placeholder="e.g. 692f1267db467ef12005e8f7" />
          </Field>

          <Field label="Nonce" hint="optional — full inventory incl. loose parts">
            <TextInput value={nonce} onChange={e => setNonce(e.target.value)}
              placeholder="from warframe-api-helper with the game running" />
          </Field>

          <Field label="Inventory file" hint="optional — inventory.json from AlecaFrame / api-helper">
            {invName ? (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 10,
                background: C.successFaint, border: `1px solid ${C.successBorder}`,
                borderRadius: 8, padding: '10px 14px', fontSize: 14,
              }}>
                <CheckCircle2 size={16} color={C.success} style={{ flexShrink: 0 }} />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: C.text }}>{invName}</span>
                <button onClick={clearInventory} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex' }}>
                  <X size={16} color={C.muted} />
                </button>
              </div>
            ) : (
              <UploadZone onClick={() => fileRef.current?.click()} />
            )}
            <input ref={fileRef} type="file" accept="application/json,.json"
              onChange={onInventory} style={{ display: 'none' }} />
          </Field>

          <Field label="Wishlist" hint="optional — one item per line; empty = everything masterable">
            <TextArea value={wishlist} onChange={e => setWishlist(e.target.value)}
              placeholder={'Caliban Prime\nVolt Prime\nSibear'} rows={3} />
          </Field>

          <Btn onClick={plan} disabled={loading} fullWidth>
            {loading
              ? <><SpinIcon />&nbsp;Planning…</>
              : <><Crosshair size={16} />&nbsp;Plan route</>}
          </Btn>

          {error && (
            <div style={{
              display: 'flex', alignItems: 'flex-start', gap: 10, marginTop: 14,
              background: C.errorFaint, border: `1px solid ${C.errorBorder}`,
              borderRadius: 8, padding: '10px 14px', fontSize: 14, color: C.error,
            }}>
              <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
              {error}
            </div>
          )}
        </Card>

        {result && <Results r={result} />}

        <footer style={{ textAlign: 'center', fontSize: 12, color: C.muted, marginTop: 32 }}>
          Unofficial fan tool · Data from{' '}
          <a href="https://docs.warframestat.us" style={{ color: C.accent }}>WFCD / warframestat</a>
          {' '}· Not affiliated with Digital Extremes
        </footer>
      </div>
    </div>
  )
}

function UploadZone({ onClick }) {
  const [hov, setHov] = useState(false)
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: 'flex', width: '100%', alignItems: 'center', justifyContent: 'center',
        gap: 8, borderRadius: 8, padding: '18px 16px', fontSize: 14, cursor: 'pointer',
        border: `2px dashed ${hov ? C.accent : C.border}`,
        color: hov ? C.accent : C.muted,
        background: hov ? C.accentFaint : 'transparent',
        transition: 'all .15s', boxSizing: 'border-box',
      }}
    >
      <Upload size={16} />
      Click to upload inventory.json
    </button>
  )
}

function SpinIcon() {
  const [deg, setDeg] = useState(0)
  React.useEffect(() => {
    const id = setInterval(() => setDeg(d => d + 6), 16)
    return () => clearInterval(id)
  }, [])
  return <Loader2 size={16} style={{ transform: `rotate(${deg}deg)` }} />
}

/* ── Results ─────────────────────────────────────────────── */

function Results({ r }) {
  if (!r.missing_equipment) {
    return (
      <Card style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <CheckCircle2 size={20} color={C.success} />
          <span>Nothing to farm — you own everything in the target set.</span>
        </div>
      </Card>
    )
  }

  const nonPrimeParts = r.non_prime.reduce((n, m) => n + m.parts.length, 0)

  return (
    <div>
      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
        <StatCard icon={<Swords size={16} color={C.gold} />}  n={r.missing_equipment} label="missing" />
        <StatCard icon={<MapPin size={16} color={C.gold} />}  n={nonPrimeParts}        label="non-prime" />
        <StatCard icon={<Gem size={16} color={C.gold} />}     n={r.prime.length}       label="prime" />
        <StatCard icon={<Lock size={16} color={C.gold} />}    n={r.vaulted_part_count} label="vaulted" />
      </div>

      {/* Non-prime */}
      {r.non_prime.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <SectionHeader icon={<MapPin size={15} color={C.gold} />}
            title={`Non-Prime — ${r.non_prime.length} mission${r.non_prime.length !== 1 ? 's' : ''}`} />
          <div style={{ padding: '0 20px 20px' }}>
            {r.non_prime.map((m, i) => (
              <div key={i}>
                {i > 0 && <div style={{ height: 1, background: C.border, margin: '4px 0' }} />}
                <MissionRow index={i + 1} mission={m} />
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Prime */}
      {r.prime.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <SectionHeader icon={<Gem size={15} color={C.gold} />}
            title={`Prime — ${r.prime.length} part${r.prime.length !== 1 ? 's' : ''}`}
            sub="Farm a relic's tier, then crack it at a void fissure." />
          <div style={{ padding: '0 20px 20px' }}>
            <div style={{
              border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden',
            }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ background: C.surface2, borderBottom: `1px solid ${C.border}` }}>
                    <th style={{ textAlign: 'left', padding: '10px 16px', color: C.muted, fontWeight: 500 }}>Part</th>
                    <th style={{ textAlign: 'left', padding: '10px 16px', color: C.muted, fontWeight: 500 }}>In-rotation relics</th>
                  </tr>
                </thead>
                <tbody>
                  {r.prime.map((p, i) => (
                    <tr key={p.part} style={i > 0 ? { borderTop: `1px solid ${C.border}` } : {}}>
                      <td style={{ padding: '10px 16px', color: C.text, fontWeight: 600, whiteSpace: 'nowrap', paddingRight: 24, verticalAlign: 'top' }}>
                        {p.part}
                      </td>
                      <td style={{ padding: '10px 16px', verticalAlign: 'top' }}>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {p.relics.map(rel => <Badge key={rel}>{rel}</Badge>)}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {r.tiers.length > 0 && (
              <div style={{ marginTop: 20 }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: C.muted, marginBottom: 10 }}>
                  Relic tiers to farm
                </div>
                {r.tiers.map(t => (
                  <div key={t.tier} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                    <TierBadge tier={t.tier} />
                    <span style={{ color: C.muted, fontSize: 14 }}>{t.where}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>
      )}

      {r.vaulted_equipment.length > 0 && (
        <CollapsibleCard icon={<Lock size={15} color={C.muted} />}
          title="Vaulted / not currently farmable" count={r.vaulted_equipment.length}>
          <ItemGrid items={r.vaulted_equipment} />
        </CollapsibleCard>
      )}

      {r.no_mission_source.length > 0 && (
        <CollapsibleCard icon={<ShoppingBag size={15} color={C.muted} />}
          title="Market / clan / syndicate / lich / Baro / quest" count={r.no_mission_source.length}>
          <ItemGrid items={r.no_mission_source} />
        </CollapsibleCard>
      )}
    </div>
  )
}

function StatCard({ icon, n, label }) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12,
      padding: 16, textAlign: 'center',
    }}>
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 6 }}>{icon}</div>
      <div style={{ fontSize: 24, fontWeight: 800, color: C.gold, lineHeight: 1 }}>{n}</div>
      <div style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>{label}</div>
    </div>
  )
}

function SectionHeader({ icon, title, sub }) {
  return (
    <div style={{ padding: '20px 20px 16px', borderBottom: `1px solid ${C.border}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: sub ? 4 : 0 }}>
        {icon}
        <span style={{ fontWeight: 700, fontSize: 15, color: C.gold }}>{title}</span>
      </div>
      {sub && <p style={{ margin: 0, fontSize: 12, color: C.muted, paddingLeft: 23 }}>{sub}</p>}
    </div>
  )
}

function MissionRow({ index, mission }) {
  return (
    <div style={{ padding: '12px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: C.muted, minWidth: 20, textAlign: 'right' }}>{index}.</span>
        <span style={{ fontWeight: 700, color: C.text }}>{mission.node}</span>
        <Badge color={C.accent} bg={C.accentFaint}>{mission.game_mode}</Badge>
      </div>
      <div style={{ paddingLeft: 28 }}>
        {mission.parts.map(p => (
          <div key={p} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <ChevronRight size={12} color={C.border} style={{ flexShrink: 0 }} />
            <span style={{ fontSize: 13, color: C.muted }}>{p}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function CollapsibleCard({ icon, title, count, children }) {
  const [open, setOpen] = useState(false)
  const [hov, setHov] = useState(false)
  return (
    <Card style={{ marginBottom: 12, overflow: 'hidden' }}>
      <button
        onClick={() => setOpen(o => !o)}
        onMouseEnter={() => setHov(true)}
        onMouseLeave={() => setHov(false)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 10,
          padding: '16px 20px', background: hov ? C.surface2 : 'transparent',
          border: 'none', cursor: 'pointer', color: C.text,
          textAlign: 'left', transition: 'background .15s',
        }}
      >
        {icon}
        <span style={{ flex: 1, fontWeight: 600, fontSize: 14 }}>{title}</span>
        <span style={{
          fontSize: 12, fontWeight: 700, padding: '2px 9px', borderRadius: 20,
          background: C.surface2, color: C.muted, border: `1px solid ${C.border}`,
        }}>{count}</span>
        <ChevronDown size={16} color={C.muted}
          style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .2s', flexShrink: 0 }} />
      </button>
      {open && (
        <div style={{ padding: '16px 20px 20px', borderTop: `1px solid ${C.border}` }}>
          {children}
        </div>
      )}
    </Card>
  )
}

function ItemGrid({ items }) {
  return (
    <div style={{ columns: '2', columnGap: 24 }}>
      {items.map(x => (
        <div key={x} style={{
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 13, color: C.muted, marginBottom: 6, breakInside: 'avoid',
        }}>
          <span style={{ width: 5, height: 5, borderRadius: '50%', background: C.border, flexShrink: 0 }} />
          {x}
        </div>
      ))}
    </div>
  )
}
