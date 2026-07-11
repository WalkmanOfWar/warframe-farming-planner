import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle, CheckCircle2, ChevronDown, ChevronRight, Clock,
  Copy, Crosshair, Gem, Loader2, Lock, MapPin, Package, ShoppingBag,
  Swords, Upload, X, Zap,
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
  event:       '#e8a020',
  eventFaint:  'rgba(232,160,32,0.10)',
  eventBorder: 'rgba(232,160,32,0.30)',
  lith:        '#2d5c35',
  meso:        '#3a3a7a',
  neo:         '#5a3a7a',
  axi:         '#7a5a2a',
  requiem:     '#5a2a2a',
}

const TIER_COLOR = { Lith: C.lith, Meso: C.meso, Neo: C.neo, Axi: C.axi, Requiem: C.requiem }

function useWindowWidth() {
  const [w, setW] = useState(typeof window !== 'undefined' ? window.innerWidth : 800)
  useEffect(() => {
    const handler = () => setW(window.innerWidth)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])
  return w
}

function lines(text) {
  return text.split('\n').map((s) => s.trim()).filter(Boolean)
}

function fmtHours(minutes) {
  if (minutes == null) return null
  const m = Math.round(minutes)
  const h = Math.floor(m / 60)
  return h ? `${h}h ${m % 60}m` : `${m}m`
}

// Inline "~N runs · ~Xh Ym" effort tag with optional hover tooltip.
function EffortTag({ runs, minutes, tooltip }) {
  const [hov, setHov] = useState(false)
  if (runs == null || minutes == null) return null
  return (
    <div style={{ position: 'relative', display: 'inline-flex' }}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}>
      <span style={{
        fontSize: 12, fontWeight: 600, color: C.accent,
        background: C.accentFaint, border: `1px solid ${C.accentBorder}`,
        borderRadius: 6, padding: '1px 8px', whiteSpace: 'nowrap', cursor: tooltip ? 'help' : 'default',
      }}>
        ~{runs} runs · ~{fmtHours(minutes)}
      </span>
      {hov && tooltip && (
        <div style={{
          position: 'absolute', bottom: 'calc(100% + 6px)', right: 0, zIndex: 10,
          background: C.surface2, border: `1px solid ${C.accentBorder}`,
          borderRadius: 8, padding: '10px 12px', minWidth: 200, maxWidth: 280,
          boxShadow: '0 4px 20px rgba(0,0,0,0.6)', fontSize: 12, lineHeight: 1.6,
          whiteSpace: 'normal',
        }}>
          {tooltip}
        </div>
      )}
    </div>
  )
}

// warframe.market average-price tag, shown only for the bounded set of
// expensive-to-farm/unfarmable items the backend actually looked up
// (r.market_prices); null renders nothing so this is safe to sprinkle
// everywhere an item name appears.
// `deals` (from r.buy_vs_farm, keyed by item name) flags parts already judged
// a bad farm-vs-buy trade-off (fully vaulted, or a long farm) — shown in red
// with the time comparison baked into the label, not just a tooltip, so it's
// impossible to miss while reading the mission/relic list itself. Anything
// merely *priced* but not flagged still gets the quieter gold tag.
function PriceTag({ name, prices, deals }) {
  const deal = deals && deals[name]
  if (deal) {
    const timeLabel = deal.minutes == null ? 'vaulted' : `vs ~${fmtHours(deal.minutes)}`
    return (
      <a href={deal.url} target="_blank" rel="noopener noreferrer"
        title={deal.minutes == null
          ? 'Vaulted — no farm route exists. Trading with another player is the only option.'
          : `Farming this run costs ~${fmtHours(deal.minutes)}${deal.shared_with > 0 ? ` (shared with ${deal.shared_with} other needed part(s))` : ''} — click to view on warframe.market`}
        style={{
          fontSize: 11, fontWeight: 700, color: C.error,
          background: C.errorFaint, border: `1px solid ${C.errorBorder}`,
          borderRadius: 6, padding: '1px 7px', textDecoration: 'none', whiteSpace: 'nowrap',
        }}>
        buy ~{deal.plat}p ({timeLabel})
      </a>
    )
  }
  const p = prices && prices[name]
  if (!p) return null
  return (
    <a href={p.url} target="_blank" rel="noopener noreferrer"
      title={`warframe.market average price${p.tradable ? '' : ' (currently untradable)'} — click to view`}
      style={{
        fontSize: 11, fontWeight: 700, color: C.gold,
        background: C.goldFaint, border: `1px solid ${C.goldBorder}`,
        borderRadius: 6, padding: '1px 7px', textDecoration: 'none', whiteSpace: 'nowrap',
      }}>
      buy ~{p.plat}p
    </a>
  )
}

// "Requires: <weapon>" tag for equipment that must be built from/with
// another whole weapon you need to already own (Akbolto needs Bolto, Dual
// Raza needs Dual Kamas, Paracesis needs Galatine, …) — surfaced from
// r.equipment_prerequisites since nothing else in the plan mentions it.
function RequiresTag({ name, prerequisites }) {
  const req = prerequisites && prerequisites[name]
  if (!req) return null
  return (
    <span title={`You must already own ${req} to build ${name}`}
      style={{
        fontSize: 11, fontWeight: 700, color: C.accent,
        background: C.accentFaint, border: `1px solid ${C.accentBorder}`,
        borderRadius: 6, padding: '1px 7px', whiteSpace: 'nowrap', cursor: 'help',
      }}>
      requires: {req}
    </span>
  )
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

function PartCheckbox({ checked, onChange, label }) {
  return (
    <input
      type="checkbox" checked={checked} onChange={onChange}
      aria-label={`Mark ${label} as collected`}
      title="Mark as collected — tracked locally, doesn't change the plan"
      style={{
        width: 15, height: 15, flexShrink: 0, accentColor: C.success, cursor: 'pointer',
      }}
    />
  )
}

function Badge({ children, color, bg, border, style }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      background: bg || C.surface2,
      color: color || C.muted,
      border: `1px solid ${border || C.border}`,
      borderRadius: 6, padding: '2px 8px',
      fontSize: 12, fontWeight: 600,
      ...style,
    }}>
      {children}
    </span>
  )
}

function SortToggle({ value, onChange, options }) {
  return (
    <div style={{ display: 'inline-flex', border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden' }}>
      {options.map(o => {
        const active = o.id === value
        return (
          <button key={o.id} onClick={() => onChange(o.id)}
            style={{
              border: 'none', cursor: 'pointer', padding: '5px 10px', fontSize: 12,
              fontWeight: 600, fontFamily: 'inherit',
              background: active ? C.accentFaint : 'transparent',
              color: active ? C.accent : C.muted,
            }}>
            {o.label}
          </button>
        )
      })}
    </div>
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

const ROT_COLOR = { A: '#3a7a4a', B: '#3a5a7a', C: '#7a3a5a' }

// Preferred display order for WFCD item type strings in grouped sections.
const TYPE_ORDER = [
  'Warframe', 'Rifle', 'Pistol', 'Dual Pistols', 'Shotgun', 'Sniper',
  'Bow', 'Launcher', 'Throwing', 'Melee',
  'Arch-Gun', 'Arch-Melee', 'Archwing',
  'Pets', 'Companion Weapon', 'Sentinel',
]

// Short acquisition hints shown under category headers in no_mission_source.
const TYPE_NOTES = {
  'Lich Weapon':   'Convert or trade a Kuva Lich',
  'Sister Weapon': 'Convert or trade a Tenet Sister',
  'Archwing':      'Archwing Exterminate / Rush missions',
}

function groupByType(keys, typeMap) {
  const groups = {}
  for (const key of keys) {
    const t = typeMap[key] || 'Other'
    ;(groups[t] = groups[t] || []).push(key)
  }
  // Sort within each group alphabetically.
  for (const k of Object.keys(groups)) groups[k].sort()
  // Return sorted by TYPE_ORDER, then unknown types alphabetically at end.
  const known = TYPE_ORDER.filter(t => groups[t])
  const unknown = Object.keys(groups).filter(t => !TYPE_ORDER.includes(t)).sort()
  return [...known, ...unknown].map(t => [t, groups[t]])
}

function RotationBadge({ rotation }) {
  if (!rotation) return null
  return (
    <span style={{
      display: 'inline-block', textAlign: 'center',
      background: ROT_COLOR[rotation] || C.surface2, color: '#fff',
      borderRadius: 6, padding: '2px 8px',
      fontSize: 11, fontWeight: 700,
    }}>
      Rot {rotation}
    </span>
  )
}

function exportText(r) {
  const lines = []
  const eff = (runs, mins) => runs != null ? `  (~${runs} runs · ~${fmtHours(mins)})` : ''

  if (r.non_prime?.length) {
    lines.push('=== NON-PRIME MISSIONS ===')
    r.non_prime.forEach((m, i) => {
      const mode = m.game_mode && m.game_mode !== 'Unknown' ? ` [${m.game_mode}]` : ''
      lines.push(`${i + 1}. ${m.node}${mode}${eff(m.runs, m.minutes)}`)
      m.parts.forEach(p => {
        const pr = (m.part_runs || {})[p]
        lines.push(`   - ${p}${pr != null ? `  (~${pr} runs)` : ''}`)
      })
    })
  }
  if (r.prime?.length) {
    lines.push('\n=== PRIME RELICS ===')
    r.prime.forEach(pr => {
      lines.push(`${pr.relic}${eff(pr.runs, pr.minutes)}`)
      pr.parts.forEach(p => lines.push(`   - ${p}`))
    })
    if (r.tiers?.length) {
      lines.push('\nRelic tiers to farm:')
      r.tiers.forEach(t => lines.push(`  ${t.tier}: ${t.where}`))
    }
  }
  if (r.vaulted_equipment?.length) {
    lines.push('\n=== VAULTED / NOT FARMABLE ===')
    r.vaulted_equipment.forEach(x => lines.push(`  - ${x}`))
  }
  if (Object.keys(r.special_source || {}).length) {
    lines.push('\n=== OTHER SOURCES ===')
    Object.entries(r.special_source).forEach(([src, parts]) => {
      lines.push(`${src}:`)
      parts.forEach(p => lines.push(`  - ${p}`))
    })
  }
  if (Object.keys(r.no_part_source || {}).length) {
    lines.push('\n=== NO DROP SOURCE (MARKET / DUVIRI / NIGHTWAVE) ===')
    Object.entries(r.no_part_source).forEach(([eq, parts]) => {
      lines.push(`${eq}:`)
      parts.forEach(p => lines.push(`  - ${p}`))
    })
  }
  if (r.no_mission_source?.length) {
    lines.push('\n=== NOT FROM MISSION DROPS ===')
    r.no_mission_source.forEach(x => lines.push(`  - ${x}`))
  }
  if (r.total_minutes != null) {
    lines.push(`\nEstimated total: ~${fmtHours(r.total_minutes)} (${r.refinement} relics${r.squad_radiant ? ', 4× squad cracking' : ', solo'})`)
  }
  return lines.join('\n')
}

/* ── Main App ─────────────────────────────────────────────── */

export default function App() {
  const w = useWindowWidth()
  const isMobile = w < 520
  const [accountId, setAccountId] = useState(() => localStorage.getItem('wf_account_id') || '')
  const [nonce, setNonce] = useState(() => localStorage.getItem('wf_nonce') || '')
  const [wishlist, setWishlist] = useState(() => {
    // A shared link carries the wishlist in the URL hash: #wl=<encoded text>.
    const m = window.location.hash.match(/^#wl=(.+)$/)
    if (m) {
      try { return decodeURIComponent(m[1]) } catch {}
    }
    return ''
  })
  const [refinement, setRefinement] = useState(() => localStorage.getItem('wf_refinement') || 'Intact')
  const [squadRadiant, setSquadRadiant] = useState(() => localStorage.getItem('wf_squad_radiant') === 'true')
  const [forceRefresh, setForceRefresh] = useState(false)

  useEffect(() => { localStorage.setItem('wf_account_id', accountId) }, [accountId])
  useEffect(() => { localStorage.setItem('wf_nonce', nonce) }, [nonce])
  useEffect(() => { localStorage.setItem('wf_refinement', refinement) }, [refinement])
  useEffect(() => { localStorage.setItem('wf_squad_radiant', squadRadiant) }, [squadRadiant])

  const [inventory, setInventory] = useState(null)
  const [invName, setInvName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [shareCopied, setShareCopied] = useState(false)
  const suggestTimer = useRef(null)

  // Autocomplete: suggest item names for the line currently being typed.
  function onWishlistChange(e) {
    const text = e.target.value
    setWishlist(text)
    clearTimeout(suggestTimer.current)
    const currentLine = text.slice(text.lastIndexOf('\n') + 1).trim()
    if (currentLine.length < 2) { setSuggestions([]); return }
    suggestTimer.current = setTimeout(async () => {
      try {
        const res = await fetch(`/api/items?q=${encodeURIComponent(currentLine)}&limit=8`)
        const data = await res.json()
        // Hide the dropdown when the line is already an exact match.
        const exact = (data.items || []).some(n => n.toLowerCase() === currentLine.toLowerCase())
        setSuggestions(exact && data.items.length === 1 ? [] : data.items || [])
      } catch { setSuggestions([]) }
    }, 200)
  }

  function pickSuggestion(name) {
    const cut = wishlist.lastIndexOf('\n') + 1
    setWishlist(wishlist.slice(0, cut) + name + '\n')
    setSuggestions([])
  }

  async function shareLink() {
    const url = `${window.location.origin}${window.location.pathname}#wl=${encodeURIComponent(wishlist.trim())}`
    try {
      await navigator.clipboard.writeText(url)
      setShareCopied(true)
      setTimeout(() => setShareCopied(false), 2000)
    } catch {}
  }
  const [result, setResult] = useState(() => {
    try { return JSON.parse(localStorage.getItem('wf_last_result') || 'null') } catch { return null }
  })
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
        refinement,
        squad_radiant: squadRadiant,
        refresh: forceRefresh,
        inventory,
      }
      const res = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Request failed')
      const stamped = { ...data, _savedAt: new Date().toISOString() }
      setResult(stamped)
      try { localStorage.setItem('wf_last_result', JSON.stringify(stamped)) } catch {}
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ background: C.bg, minHeight: '100vh', color: C.text, fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      <div style={{ maxWidth: 680, margin: '0 auto', padding: isMobile ? '24px 12px 60px' : '48px 20px 80px' }}>

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
            <div style={{
              display: 'flex', gap: 8, marginTop: 8, padding: '8px 12px',
              background: C.accentFaint, border: `1px solid ${C.accentBorder}`,
              borderRadius: 8, fontSize: 12, color: C.muted, lineHeight: 1.5,
            }}>
              <AlertCircle size={14} color={C.accent} style={{ flexShrink: 0, marginTop: 2 }} />
              <span>
                Account ID alone sees only <b>mastered</b> gear. To also subtract
                loose &amp; unbuilt parts, add a <b>Nonce</b> above or upload{' '}
                <b>inventory.json</b> — both come from{' '}
                <a href="https://alecaframe.com" target="_blank" rel="noopener noreferrer"
                  style={{ color: C.accent }}>AlecaFrame</a>{' '}or warframe-api-helper
                while the game is running (no password; the nonce dies on game exit).
              </span>
            </div>
          </Field>

          <Field label="Wishlist" hint="optional — one item per line; empty = everything masterable">
            <div style={{ position: 'relative' }}>
              <TextArea value={wishlist} onChange={onWishlistChange}
                placeholder={'Caliban Prime\nVolt Prime\nSibear'} rows={3} />
              {suggestions.length > 0 && (
                <div style={{
                  position: 'absolute', left: 0, right: 0, top: '100%', zIndex: 20,
                  background: C.surface2, border: `1px solid ${C.accentBorder}`,
                  borderRadius: 8, marginTop: 2, overflow: 'hidden',
                  boxShadow: '0 6px 24px rgba(0,0,0,0.6)',
                }}>
                  {suggestions.map(name => (
                    <button key={name} onClick={() => pickSuggestion(name)}
                      style={{
                        display: 'block', width: '100%', textAlign: 'left',
                        background: 'transparent', border: 'none', cursor: 'pointer',
                        padding: '8px 12px', fontSize: 13, color: C.text,
                        fontFamily: 'inherit',
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = C.accentFaint}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                      {name}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {wishlist.trim() && (
              <button onClick={shareLink} style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 8,
                background: 'transparent', border: `1px solid ${C.border}`,
                borderRadius: 8, padding: '5px 12px', fontSize: 12, fontWeight: 600,
                color: shareCopied ? C.success : C.muted, cursor: 'pointer',
                fontFamily: 'inherit', transition: 'color .2s',
              }}>
                {shareCopied ? <CheckCircle2 size={12} /> : <Copy size={12} />}
                {shareCopied ? 'Link copied!' : 'Copy shareable link'}
              </button>
            )}
          </Field>

          <Field label="Relic refinement" hint="for Prime effort estimate — Radiant helps rares, hurts commons">
            <select value={refinement} onChange={e => setRefinement(e.target.value)}
              style={{
                width: '100%', background: C.bg, color: C.text,
                border: `1px solid ${C.border}`, borderRadius: 8,
                padding: '10px 12px', fontSize: 14, outline: 'none',
                boxSizing: 'border-box', fontFamily: 'inherit', cursor: 'pointer',
              }}>
              {['Intact', 'Exceptional', 'Flawless', 'Radiant'].map(o =>
                <option key={o} value={o}>{o}</option>)}
            </select>
            <label style={{
              display: 'flex', alignItems: 'center', gap: 10, marginTop: 10,
              cursor: 'pointer', fontSize: 14, color: C.text,
            }}>
              <input type="checkbox" checked={squadRadiant}
                onChange={e => setSquadRadiant(e.target.checked)}
                style={{ width: 16, height: 16, accentColor: C.gold, cursor: 'pointer' }} />
              <span>
                4× squad radiant cracking
                <span style={{ marginLeft: 6, fontSize: 12, color: C.muted }}>
                  — all 4 players crack the same relic, share results
                </span>
              </span>
            </label>
            <label style={{
              display: 'flex', alignItems: 'center', gap: 10, marginTop: 8,
              cursor: 'pointer', fontSize: 14, color: C.text,
            }}>
              <input type="checkbox" checked={forceRefresh}
                onChange={e => setForceRefresh(e.target.checked)}
                style={{ width: 16, height: 16, accentColor: C.gold, cursor: 'pointer' }} />
              <span>
                Force refresh data
                <span style={{ marginLeft: 6, fontSize: 12, color: C.muted }}>
                  — re-download drop tables &amp; worldstate (bypasses 1-day cache)
                </span>
              </span>
            </label>
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

        {result && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: C.muted, flex: 1 }}>
                {result._savedAt
                  ? `Stored result from ${new Date(result._savedAt).toLocaleString()}`
                  : 'Route result'}
              </span>
              <CopyButton result={result} />
              <button onClick={() => {
                setResult(null)
                try { localStorage.removeItem('wf_last_result') } catch {}
              }} style={{
                background: 'none', border: 'none', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 4,
                color: C.muted, fontSize: 12, padding: '2px 6px',
              }}>
                <X size={12} /> Clear
              </button>
            </div>
            <Results r={result} />
          </>
        )}

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

function CopyButton({ result }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(exportText(result))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {}
  }
  return (
    <button onClick={copy} style={{
      background: 'none', border: 'none', cursor: 'pointer',
      display: 'flex', alignItems: 'center', gap: 4,
      color: copied ? C.success : C.muted, fontSize: 12, padding: '2px 6px',
      transition: 'color .2s',
    }}>
      {copied ? <CheckCircle2 size={12} /> : <Copy size={12} />}
      {copied ? 'Copied!' : 'Copy'}
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

/* ── Item icon ───────────────────────────────────────────── */

function ItemIcon({ url, name, size = 28 }) {
  const [ok, setOk] = useState(!!url)
  if (!ok) return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      width: size, height: size, borderRadius: 6,
      background: C.surface2, flexShrink: 0,
    }}>
      <Gem size={size * 0.55} color={C.border} />
    </span>
  )
  return (
    <img
      src={url} alt={name}
      onError={() => setOk(false)}
      style={{
        width: size, height: size, objectFit: 'contain',
        borderRadius: 6, background: C.surface2, flexShrink: 0,
        filter: 'drop-shadow(0 1px 3px rgba(0,0,0,0.6))',
      }}
    />
  )
}

/* ── Live fissure auto-refresh ───────────────────────────────
 * The plan snapshots which fissures are open at "Plan route" time. Fissures
 * rotate every 1–3h, so a long-lived result page goes stale. This hook polls
 * a lightweight endpoint (no full replan) and a client-side overlay recomputes
 * just the live_fissure / tier_live / farm_node_live flags — the same matching
 * logic as worldstate.fissure_node_tiers on the backend.
 */

const FISSURE_POLL_MS = 5 * 60 * 1000   // re-fetch from the server
const FISSURE_TICK_MS = 60 * 1000       // re-filter expired entries locally

function useLiveFissures() {
  const [fissures, setFissures] = useState(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function poll() {
      try {
        const res = await fetch('/api/fissures')
        const data = await res.json()
        if (!cancelled && data.fissures) setFissures(data.fissures)
      } catch { /* keep the last known snapshot on failure */ }
    }
    poll()
    const id = setInterval(poll, FISSURE_POLL_MS)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), FISSURE_TICK_MS)
    return () => clearInterval(id)
  }, [])

  return useMemo(() => {
    if (!fissures) return null
    const now = Date.now()
    return fissures.filter(f => !f.expiry || new Date(f.expiry).getTime() > now)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fissures, tick])
}

// "Adaro (Sedna)" -> {name: "Adaro", planet: "Sedna"}; storms excluded (not
// the same node concept as a regular fissure).
function fissureNodeTiers(fissures) {
  const idx = {}
  for (const f of fissures) {
    if (f.storm) continue
    const m = /^(.*)\s\(([^)]+)\)$/.exec(f.node || '')
    if (!m) continue
    idx[`${m[2].trim()}|${m[1].trim()}`.toLowerCase()] = f.tier
  }
  return idx
}

// Plan node format: "Planet - Name" or "Planet - Name · Rot X".
function missionPlanetName(node) {
  const [planet, rest = ''] = node.split(' - ')
  return { planet, name: rest.split(' · ')[0] }
}

function Results({ r }) {
  const img = r.images || {}
  const liveFissures = useLiveFissures()
  // Item name -> BuyVsFarm entry, for the stronger inline "bad trade-off" tag.
  const dealsByItem = useMemo(() => {
    const out = {}
    for (const b of r.buy_vs_farm || []) out[b.item] = b
    return out
  }, [r.buy_vs_farm])

  // Recompute the live-fissure overlay whenever a fresh poll lands; falls
  // back to the plan's own snapshot (from "Plan route" time) until the first
  // poll resolves, so the page never flashes empty.
  const liveOverlay = useMemo(() => {
    if (!liveFissures) return null
    const nodeTiers = fissureNodeTiers(liveFissures)
    const liveTiers = new Set(liveFissures.filter(f => !f.storm).map(f => f.tier))
    const missions = {}
    for (const m of r.non_prime) {
      const { planet, name } = missionPlanetName(m.node)
      missions[m.node] = nodeTiers[`${planet}|${name}`.toLowerCase()] || null
    }
    const relics = {}
    for (const pr of r.prime) {
      let farmLive = false
      if (pr.farm_node) {
        const [p, n] = pr.farm_node.split(' / ')
        farmLive = nodeTiers[`${(p || '').trim()}|${(n || '').trim()}`.toLowerCase()] === pr.tier
      }
      relics[pr.relic] = { tier_live: liveTiers.has(pr.tier), farm_node_live: farmLive }
    }
    return { missions, relics }
  }, [liveFissures, r.non_prime, r.prime])

  const nonPrimeLive = useMemo(() => (
    liveOverlay
      ? r.non_prime.map(m => ({ ...m, live_fissure: liveOverlay.missions[m.node] ?? null }))
      : r.non_prime
  ), [r.non_prime, liveOverlay])

  const primeLive = useMemo(() => (
    liveOverlay
      ? r.prime.map(pr => ({
          ...pr,
          tier_live: liveOverlay.relics[pr.relic]?.tier_live ?? pr.tier_live,
          farm_node_live: liveOverlay.relics[pr.relic]?.farm_node_live ?? pr.farm_node_live,
        }))
      : r.prime
  ), [r.prime, liveOverlay])

  const [sort, setSort] = useState('fast')
  const [groupByPlanet, setGroupByPlanet] = useState(false)
  const [search, setSearch] = useState('')
  const [showAllMissions, setShowAllMissions] = useState(false)
  const [showAllRelics, setShowAllRelics] = useState(false)
  const [checkedParts, setCheckedParts] = useState(() => {
    try { return new Set(JSON.parse(localStorage.getItem('wf_checked_parts') || '[]')) }
    catch { return new Set() }
  })
  const toggleChecked = (name) => {
    setCheckedParts(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name); else next.add(name)
      try { localStorage.setItem('wf_checked_parts', JSON.stringify([...next])) } catch {}
      return next
    })
  }
  const sq = search.trim().toLowerCase()
  const w = useWindowWidth()
  const isMobile = w < 520

  // Filter helpers — a mission or item matches if name or any sub-item matches.
  const matchStr = (s) => !sq || (s || '').toLowerCase().includes(sq)
  const matchMission = (m) =>
    matchStr(m.node) || matchStr(m.game_mode) || m.parts.some(matchStr)
  const matchRelic = (pr) =>
    matchStr(pr.relic) || pr.parts.some(matchStr)

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

  const nonPrimeParts = nonPrimeLive.reduce((n, m) => n + m.parts.length, 0)

  const allPartNames = useMemo(() => {
    const s = new Set()
    for (const m of r.non_prime) for (const p of m.parts) s.add(p)
    for (const pr of r.prime) for (const p of pr.parts) s.add(p)
    return s
  }, [r.non_prime, r.prime])
  const checkedCount = [...allPartNames].filter(p => checkedParts.has(p)).length

  // Sort key: "fast" = quickest missions first; "efficiency" = most parts per
  // run first (best bang for the buck). Unknown-effort missions sink to the end.
  const effOf = (m) => (m.runs ? m.parts.length / m.runs : -1)
  const filteredNonPrime = nonPrimeLive.filter(matchMission)
  const sortedNonPrime = [...filteredNonPrime].sort((a, b) =>
    sort === 'efficiency'
      ? effOf(b) - effOf(a)
      : (a.minutes ?? Infinity) - (b.minutes ?? Infinity))
  const TOP_N = 10
  const visibleMissions = showAllMissions || sq ? sortedNonPrime : sortedNonPrime.slice(0, TOP_N)

  const filteredPrime = primeLive.filter(matchRelic)
  const visibleRelics = showAllRelics || sq ? filteredPrime : filteredPrime.slice(0, TOP_N)
  const totalCracks = filteredPrime.reduce((s, pr) => s + (pr.cracks || 0), 0)

  const URGENCY_STYLE = {
    now:   { label: 'NOW',   color: C.error, bg: C.errorFaint, border: C.errorBorder },
    soon:  { label: 'SOON',  color: C.gold,  bg: C.goldFaint,  border: C.goldBorder },
    squad: { label: 'SQUAD', color: C.accent, bg: C.accentFaint, border: C.accentBorder },
  }

  return (
    <div>
      {/* Priority actions — what to do first */}
      {r.priority_actions?.length > 0 && (
        <div style={{
          marginBottom: 16, padding: '14px 16px',
          background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Zap size={15} color={C.gold} />
            <span style={{ fontWeight: 700, fontSize: 14, color: C.gold }}>What to do first</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {r.priority_actions.map((a, i) => {
              const s = URGENCY_STYLE[a.urgency] || URGENCY_STYLE.soon
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                  <Badge color={s.color} bg={s.bg} border={s.border} style={{
                    fontSize: 10, fontWeight: 800, letterSpacing: '0.04em', flexShrink: 0,
                    borderRadius: 5, padding: '2px 6px', marginTop: 1,
                  }}>{s.label}</Badge>
                  <div>
                    <div style={{ fontSize: 13, color: C.text, fontWeight: 600 }}>
                      {a.title}{a.expiry ? <span style={{ color: C.muted, fontWeight: 400 }}> — until {new Date(a.expiry).toLocaleString()}</span> : null}
                    </div>
                    <div style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>{a.detail}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Partial-inventory notice */}
      {r.partial_inventory && (
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: 10,
          marginBottom: 16, padding: '12px 16px',
          background: C.goldFaint, border: `1px solid ${C.goldBorder}`, borderRadius: 12,
        }}>
          <AlertCircle size={16} color={C.gold} style={{ flexShrink: 0, marginTop: 1 }} />
          <span style={{ fontSize: 13, color: C.text, lineHeight: 1.5 }}>
            Using public profile only — loose parts & unmastered gear aren't counted.
            For the full picture, add a <b>Nonce</b> or upload an <b>inventory.json</b> above.
          </span>
        </div>
      )}

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
        <StatCard icon={<Swords size={16} color={C.gold} />}  n={r.missing_equipment} label="missing" />
        <StatCard icon={<MapPin size={16} color={C.gold} />}  n={nonPrimeParts}        label="non-prime" />
        <StatCard icon={<Gem size={16} color={C.gold} />}     n={r.prime_part_count}   label="prime" />
        <StatCard icon={<Lock size={16} color={C.gold} />}    n={r.vaulted_part_count} label="vaulted" />
      </div>

      {/* Collection progress */}
      {allPartNames.size > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 12, fontSize: 12, color: C.muted,
        }}>
          <span>{checkedCount} of {allPartNames.size} part{allPartNames.size !== 1 ? 's' : ''} collected</span>
          {checkedCount > 0 && (
            <button onClick={() => {
              setCheckedParts(new Set())
              try { localStorage.removeItem('wf_checked_parts') } catch {}
            }} style={{
              background: 'none', border: 'none', color: C.accent, cursor: 'pointer',
              fontSize: 12, padding: 0, fontFamily: 'inherit',
            }}>
              Clear progress
            </button>
          )}
        </div>
      )}

      {/* Search */}
      <div style={{ position: 'relative', marginBottom: 12 }}>
        <input
          value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Filter missions, parts, relics…"
          spellCheck={false}
          style={{
            width: '100%', background: C.surface, color: C.text,
            border: `1px solid ${search ? C.accent : C.border}`,
            borderRadius: 8, padding: '9px 36px 9px 12px', fontSize: 14,
            outline: 'none', boxSizing: 'border-box', transition: 'border-color .15s',
          }}
        />
        {search && (
          <button onClick={() => setSearch('')} style={{
            position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
            background: 'none', border: 'none', cursor: 'pointer', padding: 2, display: 'flex',
          }}>
            <X size={14} color={C.muted} />
          </button>
        )}
      </div>

      {/* Estimated total time */}
      {r.total_minutes != null && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
          marginBottom: 16, padding: '12px 16px', textAlign: 'center',
          background: C.accentFaint, border: `1px solid ${C.accentBorder}`, borderRadius: 12,
        }}>
          <Clock size={16} color={C.accent} />
          <span style={{ fontSize: 14, color: C.text }}>
            Estimated total: <b style={{ color: C.accent }}>~{fmtHours(r.total_minutes)}</b>
            <span style={{ color: C.muted }}>
              {' '}· rough, {r.refinement} relics, solo cracking
            </span>
          </span>
        </div>
      )}

      {/* Do right now — actions that are both cheapest and live at this moment */}
      {!sq && (() => {
        const now = []
        const ownedLive = primeLive.filter(p => p.owned > 0 && p.tier_live)
        if (ownedLive.length) now.push(
          `Crack relics you already own (${ownedLive.map(p => `${p.relic} ×${p.owned}`).join(', ')}) — zero farming, their fissure tier is open now`)
        primeLive.filter(p => p.farm_node_live).forEach(p => now.push(
          `${(p.farm_node || '').split(' / ').pop()} is a LIVE ${p.tier} fissure — farm ${p.relic} while cracking one per run`))
        nonPrimeLive.filter(m => m.live_fissure).forEach(m => now.push(
          `Run ${m.node} as a ${m.live_fissure} fissure — farm ${m.parts.length > 1 ? 'its parts' : m.parts[0]} and crack a relic in the same mission`))
        if (!now.length) return null
        return (
          <Card accent style={{ marginBottom: 16, padding: '16px 20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <Zap size={15} color={C.gold} />
              <span style={{ fontWeight: 700, fontSize: 15, color: C.gold }}>Do right now</span>
              <span style={{ fontSize: 12, color: C.muted }}>— best value while these fissures are open</span>
            </div>
            {now.slice(0, 5).map((t, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 6, fontSize: 13, color: C.text }}>
                <span style={{ color: C.gold, fontWeight: 700 }}>{i + 1}.</span>
                <span>{t}</span>
              </div>
            ))}
          </Card>
        )
      })()}

      {/* Non-prime */}
      {nonPrimeLive.length > 0 && sortedNonPrime.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
            padding: '20px 20px 16px', borderBottom: `1px solid ${C.border}`,
          }}>
            <MapPin size={15} color={C.gold} />
            <span style={{ fontWeight: 700, fontSize: 15, color: C.gold }}>
              {`Non-Prime — ${sortedNonPrime.length}${sortedNonPrime.length < nonPrimeLive.length ? `/${nonPrimeLive.length}` : ''} mission${sortedNonPrime.length !== 1 ? 's' : ''}`}
            </span>
            <span style={{ flex: 1 }} />
            {!isMobile && <SortToggle value={sort} onChange={setSort} options={[
              { id: 'fast', label: 'Fastest first' },
              { id: 'efficiency', label: 'Most parts / run' },
            ]} />}
          </div>
          {isMobile && (
            <div style={{ padding: '10px 20px 0', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <SortToggle value={sort} onChange={setSort} options={[
                { id: 'fast', label: 'Fastest' },
                { id: 'efficiency', label: 'Efficient' },
              ]} />
              <button onClick={() => setGroupByPlanet(g => !g)} style={{
                border: `1px solid ${groupByPlanet ? C.accentBorder : C.border}`,
                background: groupByPlanet ? C.accentFaint : 'transparent',
                color: groupByPlanet ? C.accent : C.muted,
                borderRadius: 8, padding: '5px 10px', fontSize: 12, fontWeight: 600,
                cursor: 'pointer', fontFamily: 'inherit',
              }}>By planet</button>
            </div>
          )}
          {!isMobile && (
            <div style={{ padding: '8px 20px 0', display: 'flex', gap: 8 }}>
              <button onClick={() => setGroupByPlanet(g => !g)} style={{
                border: `1px solid ${groupByPlanet ? C.accentBorder : C.border}`,
                background: groupByPlanet ? C.accentFaint : 'transparent',
                color: groupByPlanet ? C.accent : C.muted,
                borderRadius: 8, padding: '4px 10px', fontSize: 12, fontWeight: 600,
                cursor: 'pointer', fontFamily: 'inherit',
              }}>Group by planet</button>
            </div>
          )}
          <div style={{ padding: '0 20px 20px' }}>
            {groupByPlanet
              ? (() => {
                  const byPlanet = {}
                  visibleMissions.forEach(m => {
                    const planet = m.node.split(' - ')[0] || 'Unknown'
                    ;(byPlanet[planet] = byPlanet[planet] || []).push(m)
                  })
                  return Object.entries(byPlanet).sort(([a], [b]) => a.localeCompare(b)).map(([planet, missions]) => (
                    <div key={planet}>
                      <div style={{
                        fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
                        textTransform: 'uppercase', color: C.accent, margin: '16px 0 6px',
                        borderBottom: `1px solid ${C.accentBorder}`, paddingBottom: 4,
                      }}>{planet}</div>
                      {missions.map((m, i) => (
                        <div key={m.node}>
                          {i > 0 && <div style={{ height: 1, background: C.border, margin: '4px 0' }} />}
                          <MissionRow index={i + 1} mission={m} images={img} search={sq} prices={r.market_prices} deals={dealsByItem} checkedParts={checkedParts} onToggleChecked={toggleChecked} />
                        </div>
                      ))}
                    </div>
                  ))
                })()
              : visibleMissions.map((m, i) => (
                  <div key={m.node}>
                    {i > 0 && <div style={{ height: 1, background: C.border, margin: '4px 0' }} />}
                    <MissionRow index={i + 1} mission={m} images={img} search={sq} prices={r.market_prices} checkedParts={checkedParts} onToggleChecked={toggleChecked} />
                  </div>
                ))
            }
            {!showAllMissions && !sq && sortedNonPrime.length > TOP_N && (
              <button onClick={() => setShowAllMissions(true)} style={{
                display: 'block', width: '100%', marginTop: 12, padding: '8px 0',
                background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8,
                color: C.muted, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit',
              }}>
                Show all {sortedNonPrime.length} missions (hiding {sortedNonPrime.length - TOP_N} more)
              </button>
            )}
          </div>
        </Card>
      )}

      {/* Non-prime uncovered parts */}
      {r.non_prime_uncovered?.length > 0 && !sq && (
        <CollapsibleCard
          icon={<AlertCircle size={15} color={C.error} />}
          title="Parts with no routeable mission node"
          count={r.non_prime_uncovered.length}
          accentColor={C.error}>
          <p style={{ margin: '0 0 12px', fontSize: 13, color: C.muted }}>
            These parts have drop data in the database but no planet/node location the optimizer can route. They may come from special sources not in the standard mission list.
          </p>
          <ItemGrid items={r.non_prime_uncovered} images={img} />
        </CollapsibleCard>
      )}

      {/* Prime */}
      {primeLive.length > 0 && filteredPrime.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <SectionHeader icon={<Gem size={15} color={C.gold} />}
            title={`Prime — crack ${filteredPrime.length}${filteredPrime.length < primeLive.length ? `/${primeLive.length}` : ''} relic${filteredPrime.length !== 1 ? 's' : ''} for ${r.prime_part_count} part${r.prime_part_count !== 1 ? 's' : ''}`}
            sub={`Farm each relic's tier, crack at a void fissure. Shared-part relics are cracked once.${totalCracks > 0 ? ` Total fissure runs: ~${Math.round(totalCracks)}.` : ''}${r.squad_radiant ? ' 4× squad Radiant model.' : ''}`} />
          <div style={{ padding: '0 20px 20px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {visibleRelics.map((pr, i) => {
                const farmLabel = pr.farm_node
                  ? `${pr.farm_node.split(' / ').pop()} (${pr.farm_node.split(' / ')[0]}) · ${pr.farm_mode}${pr.farm_chance ? ` · ${pr.farm_chance}%` : ''}`
                  : null
                const relicTooltip = pr.cracks != null
                  ? <><div style={{ fontWeight: 700, color: C.text, marginBottom: 6 }}>Effort breakdown:</div>
                      <div style={{ color: C.muted, marginBottom: 2 }}>~{pr.cracks} cracks to get all parts</div>
                      <div style={{ color: C.muted, marginBottom: farmLabel ? 8 : 0 }}>~{pr.runs} total runs (farm + crack)</div>
                      {farmLabel && <div style={{ color: C.accent, fontSize: 11 }}>Best farm: {farmLabel}</div>}</>
                  : null
                return (
                <div key={pr.relic}>
                  {i > 0 && <div style={{ height: 1, background: C.border, margin: '4px 0' }} />}
                  <div style={{ padding: '12px 0' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                      <TierBadge tier={pr.tier} />
                      <span style={{ fontWeight: 700, color: C.text }}>{pr.relic}</span>
                      {pr.cracks != null && (
                        <span style={{ fontSize: 12, color: C.muted }}>~{pr.cracks} cracks</span>
                      )}
                      {pr.owned > 0 && (
                        <span style={{
                          fontSize: 11, fontWeight: 700, color: C.success,
                          background: C.successFaint, border: `1px solid ${C.successBorder}`,
                          borderRadius: 6, padding: '1px 7px',
                        }}>own {pr.owned}</span>
                      )}
                      {pr.best_refinement && (
                        <span title={`Refining changes in-relic chances; for this relic ${pr.best_refinement} minimizes total time (traces: Exceptional 25 / Flawless 50 / Radiant 100).`}
                          style={{
                            fontSize: 11, fontWeight: 700, color: C.event,
                            background: C.eventFaint, border: `1px solid ${C.eventBorder}`,
                            borderRadius: 6, padding: '1px 7px', cursor: 'help',
                          }}>
                          crack as {pr.best_refinement} → ~{fmtHours(pr.best_refinement_minutes)}
                        </span>
                      )}
                      <span style={{ flex: 1 }} />
                      <EffortTag runs={pr.runs} minutes={pr.minutes} tooltip={relicTooltip} />
                    </div>
                    {farmLabel && (
                      <div style={{ fontSize: 11, color: C.muted, paddingLeft: 4, marginBottom: 8, opacity: 0.8 }}>
                        Farm at: <span style={{ color: C.accent }}>{farmLabel}</span>
                        {pr.farm_node_live && (
                          <span style={{ color: C.success, fontWeight: 700, marginLeft: 8 }}>
                            ⚡ LIVE {pr.tier} fissure — farm &amp; crack together!
                          </span>
                        )}
                        {!pr.farm_node_live && pr.tier_live && (
                          <span style={{ color: C.success, marginLeft: 8 }}>
                            · {pr.tier} fissure open now
                          </span>
                        )}
                      </div>
                    )}
                    <div style={{ paddingLeft: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {pr.parts.map(p => {
                        const done = checkedParts.has(p)
                        return (
                          <div key={p} style={{ display: 'flex', alignItems: 'center', gap: 8, opacity: done ? 0.5 : 1 }}>
                            <PartCheckbox checked={done} onChange={() => toggleChecked(p)} label={p} />
                            <ItemIcon url={img[p]} name={p} size={24} />
                            <span style={{ fontSize: 13, color: C.muted, textDecoration: done ? 'line-through' : 'none' }}>{p}</span>
                            <PriceTag name={p} prices={r.market_prices} deals={dealsByItem} />
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </div>
              )})}
              {!showAllRelics && !sq && filteredPrime.length > TOP_N && (
                <button onClick={() => setShowAllRelics(true)} style={{
                  display: 'block', width: '100%', marginTop: 8, padding: '8px 0',
                  background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8,
                  color: C.muted, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit',
                }}>
                  Show all {filteredPrime.length} relics (hiding {filteredPrime.length - TOP_N} more)
                </button>
              )}
            </div>

            {r.tiers.length > 0 && (() => {
              const tierRuns = {}, tierMins = {}
              filteredPrime.forEach(pr => {
                if (pr.runs != null) tierRuns[pr.tier] = (tierRuns[pr.tier] || 0) + pr.runs
                if (pr.minutes != null) tierMins[pr.tier] = (tierMins[pr.tier] || 0) + pr.minutes
              })
              return (
                <div style={{ marginTop: 20 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: C.muted, marginBottom: 10 }}>
                    Relic tiers to farm
                  </div>
                  {r.tiers.map(t => (
                    <div key={t.tier} style={{ marginBottom: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                        <TierBadge tier={t.tier} />
                        <span style={{ color: C.muted, fontSize: 14, flex: 1 }}>{t.where}</span>
                        {tierRuns[t.tier] != null && (
                          <span style={{ fontSize: 12, color: C.accent, fontWeight: 600 }}>
                            ~{Math.round(tierRuns[t.tier])} runs{tierMins[t.tier] != null ? ` · ~${fmtHours(tierMins[t.tier])}` : ''}
                          </span>
                        )}
                      </div>
                      {(r.active_fissures?.[t.tier] || []).slice(0, 3).map(f => (
                        <div key={f.node + f.mission} style={{
                          display: 'flex', alignItems: 'center', gap: 6,
                          paddingLeft: 76, fontSize: 12, color: C.muted, marginTop: 3,
                        }}>
                          <span style={{
                            width: 6, height: 6, borderRadius: '50%',
                            background: C.success, flexShrink: 0,
                          }} />
                          <span style={{ color: C.success, fontWeight: 700, fontSize: 10, letterSpacing: '0.06em' }}>LIVE</span>
                          <span>{f.node} · {f.mission}</span>
                          {f.hard && <span style={{ color: C.event, fontSize: 10, fontWeight: 700 }}>STEEL PATH</span>}
                          {f.storm && <span style={{ color: C.accent, fontSize: 10, fontWeight: 700 }}>VOID STORM</span>}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )
            })()}
          </div>
        </Card>
      )}

      {r.buy_vs_farm?.length > 0 && (
        <Card style={{ marginBottom: 16, borderColor: C.goldBorder }}>
          <div style={{ padding: '16px 20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <Gem size={15} color={C.gold} />
              <span style={{ fontWeight: 700, fontSize: 15, color: C.gold }}>
                Buy instead of farm — worst trade-offs first
              </span>
            </div>
            <div style={{ fontSize: 12, color: C.muted, marginBottom: 12 }}>
              warframe.market average price vs. what farming it would actually cost.
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {r.buy_vs_farm.map(b => (
                <div key={b.item} style={{
                  display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                }}>
                  <ItemIcon url={img[b.item]} name={b.item} size={24} />
                  <span style={{ fontSize: 13, color: C.text, minWidth: 0 }}>{b.item}</span>
                  <span style={{ flex: 1 }} />
                  {b.minutes == null ? (
                    <span style={{
                      fontSize: 11, fontWeight: 700, color: C.error,
                      background: C.errorFaint, border: `1px solid ${C.errorBorder}`,
                      borderRadius: 6, padding: '1px 7px',
                    }}>vaulted — no farm route</span>
                  ) : (
                    <span style={{ fontSize: 12, color: C.muted }} title={
                      b.shared_with > 0
                        ? `Farming ${b.source} costs ~${fmtHours(b.minutes)}, but that run also covers ${b.shared_with} other needed part(s) — buying this alone won't remove it from your route.`
                        : `Farming ${b.source} costs ~${fmtHours(b.minutes)} for this part alone.`
                    }>
                      vs ~{fmtHours(b.minutes)} farming{b.shared_with > 0 ? ` (shared×${b.shared_with + 1})` : ''}
                    </span>
                  )}
                  {b.url ? (
                    <a href={b.url} target="_blank" rel="noopener noreferrer"
                      title={`warframe.market average price${b.tradable ? '' : ' (currently untradable)'} — click to view`}
                      style={{
                        fontSize: 12, fontWeight: 700, color: C.gold,
                        background: C.goldFaint, border: `1px solid ${C.goldBorder}`,
                        borderRadius: 6, padding: '2px 9px', textDecoration: 'none', whiteSpace: 'nowrap',
                      }}>
                      buy ~{b.plat}p
                    </a>
                  ) : (
                    <span style={{
                      fontSize: 12, fontWeight: 700, color: C.gold,
                      background: C.goldFaint, border: `1px solid ${C.goldBorder}`,
                      borderRadius: 6, padding: '2px 9px', whiteSpace: 'nowrap',
                    }}>~{b.plat}p</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}

      {r.resource_needs?.length > 0 && (() => {
        const hasDeficit = r.resource_needs.some(x => x.short_by != null)
        const rows = hasDeficit ? r.resource_needs.filter(x => (x.short_by ?? 0) > 0) : r.resource_needs
        if (!rows.length) return null
        return (
          <CollapsibleCard icon={<Package size={15} color={C.accent} />}
            title={hasDeficit ? "Crafting resources you're still short on" : "Crafting resources needed (totals)"}
            count={rows.length} accentColor={C.accent}>
            <p style={{ margin: '0 0 12px', fontSize: 13, color: C.muted }}>
              From a separate source (Warframe Wiki) than the rest of this plan — WFCD doesn't
              track build costs. Covers ~70% of items; anything not listed here has no known recipe data.
              {r.credits_needed ? <> Also needs <b style={{ color: C.text }}>~{r.credits_needed.toLocaleString()}</b> credits total.</> : null}
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {rows.map(x => (
                <div key={x.resource} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 13, color: C.text, flex: 1 }}>{x.resource}</span>
                  {x.short_by != null ? (
                    <span style={{ fontSize: 12, color: C.muted }}>
                      have <b style={{ color: C.text }}>{x.owned}</b> / need <b style={{ color: C.text }}>{x.need}</b>
                      {' — '}
                      <span style={{ color: C.error, fontWeight: 700 }}>short {x.short_by}</span>
                    </span>
                  ) : (
                    <span style={{ fontSize: 13, fontWeight: 700, color: C.accent }}>{x.need}</span>
                  )}
                </div>
              ))}
            </div>
          </CollapsibleCard>
        )
      })()}

      {r.baro && (
        <Card style={{ marginBottom: 16, borderColor: C.eventBorder }}>
          <div style={{ padding: '16px 20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <ShoppingBag size={15} color={C.event} />
              <span style={{ fontWeight: 700, fontSize: 15, color: C.event }}>
                Baro Ki'Teer has {r.baro.items.length} item{r.baro.items.length !== 1 ? 's' : ''} you need
              </span>
            </div>
            <div style={{ fontSize: 12, color: C.muted, marginBottom: 10 }}>
              At {r.baro.location}
              {r.baro.until ? ` · leaves ${new Date(r.baro.until).toLocaleString()}` : ''}
            </div>
            <ItemGrid items={r.baro.items} images={img} />
          </div>
        </Card>
      )}

      {r.daily_deal && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16,
          padding: '10px 16px', background: C.accentFaint,
          border: `1px solid ${C.accentBorder}`, borderRadius: 12, fontSize: 13,
        }}>
          <Zap size={14} color={C.accent} />
          <span style={{ color: C.text }}>
            Darvo's daily deal: <b>{r.daily_deal.item}</b>
            {r.daily_deal.discount != null && ` — ${r.daily_deal.discount}% off`}
          </span>
        </div>
      )}

      {r.vaulted_crackable?.length > 0 && (
        <CollapsibleCard icon={<Gem size={15} color={C.success} />}
          title="Vaulted parts you can still crack — you own the relic"
          count={r.vaulted_crackable.length} accentColor={C.success}>
          <p style={{ margin: '0 0 12px', fontSize: 13, color: C.muted }}>
            These relics no longer drop anywhere, but copies already in your vault
            can be cracked at any matching void fissure.
          </p>
          {r.vaulted_crackable.map(c => (
            <div key={`${c.part}-${c.relic}`} style={{
              display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap',
            }}>
              <ItemIcon url={img[c.part]} name={c.part} size={24} />
              <span style={{ fontSize: 13, color: C.text, flex: 1, minWidth: 160 }}>{c.part}</span>
              <span style={{ fontSize: 12, color: C.muted }}>{c.relic}</span>
              <span style={{
                fontSize: 11, fontWeight: 700, color: C.success,
                background: C.successFaint, border: `1px solid ${C.successBorder}`,
                borderRadius: 6, padding: '1px 7px',
              }}>own {c.owned}</span>
              <span style={{ fontSize: 11, color: C.accent }}>{c.chance}% / crack</span>
            </div>
          ))}
        </CollapsibleCard>
      )}

      {r.vaulted_equipment.length > 0 && (
        <CollapsibleCard icon={<Lock size={15} color={C.muted} />}
          title="Vaulted / not currently farmable" count={r.vaulted_equipment.length}>
          <ItemGrid items={r.vaulted_equipment} images={img} prices={r.market_prices} deals={dealsByItem} />
        </CollapsibleCard>
      )}

      {r.no_mission_source.length > 0 && (
        <CollapsibleCard icon={<ShoppingBag size={15} color={C.muted} />}
          title="Market / clan / syndicate / lich / Baro / quest" count={r.no_mission_source.length}>
          {groupByType(r.no_mission_source, r.item_types || {}).map(([type, items]) => (
            <div key={type} style={{ marginBottom: 16 }}>
              <TypeLabel label={type} note={TYPE_NOTES[type]} />
              <ItemGrid items={items} images={img} prerequisites={r.equipment_prerequisites} />
            </div>
          ))}
        </CollapsibleCard>
      )}

      {Object.keys(r.no_part_source || {}).length > 0 && (
        <CollapsibleCard icon={<ShoppingBag size={15} color={C.gold} />}
          title="No drop source in database (Market / Duviri / Nightwave / etc.)"
          count={Object.values(r.no_part_source).reduce((s, a) => s + a.length, 0)}>
          {groupByType(Object.keys(r.no_part_source), r.item_types || {}).map(([type, equips]) => (
            <div key={type} style={{ marginBottom: 20 }}>
              <TypeLabel label={type} />
              {equips.map(equip => (
                <div key={equip} style={{ marginBottom: 12, paddingLeft: 4 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    fontSize: 12, fontWeight: 600, color: C.gold, marginBottom: 6,
                  }}>
                    {equip}
                    <RequiresTag name={equip} prerequisites={r.equipment_prerequisites} />
                  </div>
                  <ItemGrid items={r.no_part_source[equip]} images={img} />
                </div>
              ))}
            </div>
          ))}
        </CollapsibleCard>
      )}

      {Object.keys(r.special_source || {}).length > 0 && (
        <CollapsibleCard
          icon={<Crosshair size={15} color={C.accent} />}
          title="Other sources (Sanctuary Onslaught / Plains / etc.)"
          count={Object.values(r.special_source).reduce((s, a) => s + a.length, 0)}>
          {Object.entries(r.special_source).map(([src, parts]) => (
            <div key={src} style={{ marginBottom: 16 }}>
              <div style={{
                fontSize: 11, fontWeight: 600, letterSpacing: '0.06em',
                color: C.accent, textTransform: 'uppercase', marginBottom: 8,
              }}>{src}</div>
              <ItemGrid items={parts} images={img} />
            </div>
          ))}
        </CollapsibleCard>
      )}

      {Object.keys(r.event_source || {}).length > 0 && (
        <CollapsibleCard
          icon={<Zap size={15} color={C.event} />}
          title="Also available from current events / alerts"
          count={Object.values(r.event_source).reduce((s, a) => s + a.length, 0)}
          accentColor={C.event}>
          <p style={{ margin: '0 0 14px', fontSize: 13, color: C.muted }}>
            These needed items also drop from transient / rotating objectives active right now.
            Grinding them gives you progress on multiple goals simultaneously.
          </p>
          {Object.entries(r.event_source).map(([src, its]) => (
            <div key={src} style={{ marginBottom: 14 }}>
              <div style={{
                fontSize: 11, fontWeight: 600, letterSpacing: '0.06em',
                color: C.event, textTransform: 'uppercase', marginBottom: 8,
              }}>{src}</div>
              <ItemGrid items={its} images={img} />
            </div>
          ))}
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

function Highlight({ text, query }) {
  if (!query) return <>{text}</>
  const idx = text.toLowerCase().indexOf(query)
  if (idx < 0) return <>{text}</>
  return (
    <>
      {text.slice(0, idx)}
      <mark style={{ background: 'rgba(212,179,90,0.35)', color: C.text, borderRadius: 2, padding: '0 1px' }}>
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  )
}

function MissionRow({ index, mission, images = {}, search = '', prices = {}, deals = {}, checkedParts = new Set(), onToggleChecked = () => {} }) {
  const partRunEntries = Object.entries(mission.part_runs || {}).filter(([, r]) => r != null)
  const tooltip = partRunEntries.length > 1
    ? <><div style={{ fontWeight: 700, color: C.text, marginBottom: 6 }}>Per-part expected runs:</div>
        {partRunEntries.map(([p, r]) => (
          <div key={p} style={{ color: C.muted, marginBottom: 2 }}>
            <span style={{ color: C.accent }}>~{r}×</span> {p}
          </div>
        ))}</>
    : null

  return (
    <div style={{ padding: '12px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: C.muted, minWidth: 20, textAlign: 'right' }}>{index}.</span>
        <span style={{ fontWeight: 700, color: C.text }}>
          <Highlight text={mission.node} query={search} />
        </span>
        {mission.game_mode && mission.game_mode !== 'Unknown' && (
          <Badge color={C.accent} bg={C.accentFaint}>{mission.game_mode}</Badge>
        )}
        {mission.rotation && <RotationBadge rotation={mission.rotation} />}
        {mission.live_fissure && (
          <span title="This node is an open void fissure right now — run it as a fissure with a relic equipped to farm the part AND crack a relic in one mission."
            style={{
              fontSize: 11, fontWeight: 700, color: C.success,
              background: C.successFaint, border: `1px solid ${C.successBorder}`,
              borderRadius: 6, padding: '1px 7px', cursor: 'help',
            }}>
            ⚡ LIVE {mission.live_fissure} fissure
          </span>
        )}
        <span style={{ flex: 1 }} />
        <EffortTag runs={mission.runs} minutes={mission.minutes} tooltip={tooltip} />
      </div>
      <div style={{ paddingLeft: 28, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {mission.parts.map(p => {
          const pr = (mission.part_runs || {})[p]
          const done = checkedParts.has(p)
          return (
            <div key={p} style={{ display: 'flex', alignItems: 'center', gap: 8, opacity: done ? 0.5 : 1 }}>
              <PartCheckbox checked={done} onChange={() => onToggleChecked(p)} label={p} />
              <ItemIcon url={images[p]} name={p} size={24} />
              <span style={{ fontSize: 13, color: C.muted, textDecoration: done ? 'line-through' : 'none' }}>
                <Highlight text={p} query={search} />
              </span>
              {pr != null && (
                <span style={{ fontSize: 11, color: C.muted, opacity: 0.7 }}>~{pr} runs</span>
              )}
              <PriceTag name={p} prices={prices} deals={deals} />
            </div>
          )
        })}
      </div>
    </div>
  )
}

function CollapsibleCard({ icon, title, count, children, accentColor }) {
  const [open, setOpen] = useState(false)
  const [hov, setHov] = useState(false)
  const countColor = accentColor || C.muted
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
          background: C.surface2, color: countColor, border: `1px solid ${C.border}`,
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

function TypeLabel({ label, note }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'baseline', gap: 8,
      borderBottom: `1px solid ${C.border}`,
      paddingBottom: 4, marginBottom: 10,
    }}>
      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: C.muted }}>
        {label}
      </span>
      {note && <span style={{ fontSize: 11, color: C.muted, opacity: 0.7 }}>{note}</span>}
    </div>
  )
}

function ItemGrid({ items, images = {}, prices = {}, deals = {}, prerequisites = {} }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
      gap: '6px 16px',
    }}>
      {items.map(x => (
        <div key={x} style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <ItemIcon url={images[x]} name={x} size={24} />
          <span style={{ fontSize: 13, color: C.muted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{x}</span>
          <PriceTag name={x} prices={prices} deals={deals} />
          <RequiresTag name={x} prerequisites={prerequisites} />
        </div>
      ))}
    </div>
  )
}
