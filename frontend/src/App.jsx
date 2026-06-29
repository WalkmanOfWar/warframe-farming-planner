import React, { useRef, useState } from 'react'
import {
  AlertCircle, CheckCircle2, ChevronDown, ChevronRight,
  Crosshair, Gem, Loader2, Lock, MapPin, ShoppingBag,
  Swords, Upload, X,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

const API = '/api/route'

function lines(text) {
  return text.split('\n').map((s) => s.trim()).filter(Boolean)
}

const TIER_VARIANT = { Lith: 'lith', Meso: 'meso', Neo: 'neo', Axi: 'axi', Requiem: 'requiem' }

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
    <div style={{ background: 'var(--color-bg)' }} className="min-h-screen">
      <div className="max-w-2xl mx-auto px-5 py-10 pb-20">

        {/* Header */}
        <header className="mb-8 text-center">
          <div className="inline-flex items-center justify-center size-14 rounded-2xl mb-4"
               style={{ background: 'var(--color-gold-faint)', border: '1px solid rgba(212,179,90,0.25)' }}>
            <Swords className="size-7" style={{ color: 'var(--color-gold)' }} />
          </div>
          <h1 className="text-3xl font-bold mb-2" style={{ color: 'var(--color-gold)' }}>
            Warframe Farming Planner
          </h1>
          <p className="text-sm" style={{ color: 'var(--color-muted)' }}>
            Plan the fewest missions to farm everything you're still missing.
          </p>
        </header>

        {/* Form card */}
        <Card accent className="mb-6">
          <CardHeader>
            <CardTitle>
              <Crosshair className="size-4" />
              Your profile
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">

            <Field label="Account ID" hint="24-hex gid cookie, not username">
              <Input
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                placeholder="e.g. 692f1267db467ef12005e8f7"
                spellCheck={false}
              />
            </Field>

            <Field label="Nonce" hint="optional — full inventory incl. loose parts">
              <Input
                value={nonce}
                onChange={(e) => setNonce(e.target.value)}
                placeholder="from warframe-api-helper with the game running"
                spellCheck={false}
              />
            </Field>

            <Field label="Inventory file" hint="optional — inventory.json from AlecaFrame / api-helper">
              {invName ? (
                <div className="flex items-center gap-3 rounded-lg px-4 py-3 text-sm"
                     style={{ background: 'rgba(63,185,80,0.08)', border: '1px solid rgba(63,185,80,0.3)' }}>
                  <CheckCircle2 className="size-4 shrink-0" style={{ color: 'var(--color-success)' }} />
                  <span className="flex-1 truncate" style={{ color: 'var(--color-text)' }}>{invName}</span>
                  <button onClick={clearInventory} className="transition-opacity hover:opacity-70">
                    <X className="size-4" style={{ color: 'var(--color-muted)' }} />
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => fileRef.current?.click()}
                  className="flex w-full items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-5 text-sm transition-colors cursor-pointer"
                  style={{
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-muted)',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.borderColor = 'var(--color-accent)'
                    e.currentTarget.style.color = 'var(--color-accent)'
                    e.currentTarget.style.background = 'var(--color-accent-faint)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.borderColor = 'var(--color-border)'
                    e.currentTarget.style.color = 'var(--color-muted)'
                    e.currentTarget.style.background = 'transparent'
                  }}
                >
                  <Upload className="size-4" />
                  Click to upload inventory.json
                </button>
              )}
              <input ref={fileRef} type="file" accept="application/json,.json"
                     onChange={onInventory} className="hidden" />
            </Field>

            <Field label="Wishlist" hint="optional — one item per line; empty = everything masterable">
              <Textarea
                rows={3}
                value={wishlist}
                onChange={(e) => setWishlist(e.target.value)}
                placeholder={'Caliban Prime\nVolt Prime\nSibear'}
              />
            </Field>

            <Button onClick={plan} disabled={loading} size="lg" className="w-full mt-2">
              {loading
                ? <><Loader2 className="size-4 animate-spin" /> Planning…</>
                : <><Crosshair className="size-4" /> Plan route</>}
            </Button>

            {error && (
              <div className="flex items-start gap-3 rounded-lg px-4 py-3 text-sm"
                   style={{ background: 'rgba(248,81,73,0.08)', border: '1px solid rgba(248,81,73,0.3)', color: 'var(--color-error)' }}>
                <AlertCircle className="size-4 mt-0.5 shrink-0" />
                {error}
              </div>
            )}
          </CardContent>
        </Card>

        {result && <Results r={result} />}

        <footer className="text-center text-xs mt-10" style={{ color: 'var(--color-muted)' }}>
          Unofficial fan tool · Data from{' '}
          <a href="https://docs.warframestat.us" style={{ color: 'var(--color-accent)' }}
             className="hover:underline">WFCD / warframestat</a>
          {' '}· Not affiliated with Digital Extremes
        </footer>
      </div>
    </div>
  )
}

/* ── Small helpers ────────────────────────────────────────── */

function Field({ label, hint, children }) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2 flex-wrap">
        <Label style={{ color: 'var(--color-text)', fontWeight: 600 }}>{label}</Label>
        {hint && <span className="text-xs" style={{ color: 'var(--color-muted)' }}>{hint}</span>}
      </div>
      {children}
    </div>
  )
}

/* ── Results ─────────────────────────────────────────────── */

function Results({ r }) {
  if (!r.missing_equipment) {
    return (
      <Card className="mb-4">
        <CardContent className="pt-6 flex items-center gap-3">
          <CheckCircle2 className="size-5" style={{ color: 'var(--color-success)' }} />
          <span>Nothing to farm — you own everything in the target set.</span>
        </CardContent>
      </Card>
    )
  }

  const nonPrimeParts = r.non_prime.reduce((n, m) => n + m.parts.length, 0)

  return (
    <div className="space-y-4">
      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard icon={<Swords className="size-4" />}  n={r.missing_equipment} label="missing items" />
        <StatCard icon={<MapPin className="size-4" />}  n={nonPrimeParts}        label="non-prime parts" />
        <StatCard icon={<Gem className="size-4" />}     n={r.prime.length}       label="prime parts" />
        <StatCard icon={<Lock className="size-4" />}    n={r.vaulted_part_count} label="vaulted parts" />
      </div>

      {/* Non-prime missions */}
      {r.non_prime.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              <MapPin className="size-4" />
              Non-Prime — {r.non_prime.length} mission{r.non_prime.length !== 1 ? 's' : ''}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 space-y-0">
            {r.non_prime.map((m, i) => (
              <div key={i}>
                {i > 0 && <Separator />}
                <MissionRow index={i + 1} mission={m} />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Prime parts */}
      {r.prime.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              <Gem className="size-4" />
              Prime — {r.prime.length} part{r.prime.length !== 1 ? 's' : ''}
            </CardTitle>
            <p className="text-xs mt-1" style={{ color: 'var(--color-muted)' }}>
              Farm a relic's <strong style={{ color: 'var(--color-text)' }}>tier</strong>, then crack it at a void fissure.
            </p>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--color-border)' }}>
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-surface2)' }}>
                    <th className="text-left px-4 py-2.5 font-medium" style={{ color: 'var(--color-muted)' }}>Part</th>
                    <th className="text-left px-4 py-2.5 font-medium" style={{ color: 'var(--color-muted)' }}>In-rotation relics</th>
                  </tr>
                </thead>
                <tbody>
                  {r.prime.map((p, i) => (
                    <tr key={p.part} style={i > 0 ? { borderTop: '1px solid var(--color-border)' } : {}}>
                      <td className="px-4 py-3 font-medium align-top whitespace-nowrap pr-6"
                          style={{ color: 'var(--color-text)' }}>
                        {p.part}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1.5">
                          {p.relics.map((rel) => (
                            <Badge key={rel} variant="relic">{rel}</Badge>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {r.tiers.length > 0 && (
              <div className="mt-5">
                <p className="text-xs font-semibold uppercase tracking-widest mb-3"
                   style={{ color: 'var(--color-muted)' }}>
                  Relic tiers to farm
                </p>
                <div className="space-y-2">
                  {r.tiers.map((t) => (
                    <div key={t.tier} className="flex items-center gap-3 text-sm">
                      <Badge variant={TIER_VARIANT[t.tier] ?? 'default'}
                             className="min-w-[58px] justify-center">
                        {t.tier}
                      </Badge>
                      <span style={{ color: 'var(--color-muted)' }}>{t.where}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Vaulted */}
      {r.vaulted_equipment.length > 0 && (
        <CollapsibleCard
          icon={<Lock className="size-4" />}
          title="Vaulted / not currently farmable"
          count={r.vaulted_equipment.length}
        >
          <ItemGrid items={r.vaulted_equipment} />
        </CollapsibleCard>
      )}

      {/* No mission source */}
      {r.no_mission_source.length > 0 && (
        <CollapsibleCard
          icon={<ShoppingBag className="size-4" />}
          title="Market / clan / syndicate / lich / Baro / quest"
          count={r.no_mission_source.length}
        >
          <ItemGrid items={r.no_mission_source} />
        </CollapsibleCard>
      )}
    </div>
  )
}

function StatCard({ icon, n, label }) {
  return (
    <div className="rounded-xl p-4 text-center"
         style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
      <div className="flex justify-center mb-1.5" style={{ color: 'var(--color-gold)' }}>{icon}</div>
      <div className="text-2xl font-bold" style={{ color: 'var(--color-gold)' }}>{n}</div>
      <div className="text-xs mt-0.5" style={{ color: 'var(--color-muted)' }}>{label}</div>
    </div>
  )
}

function MissionRow({ index, mission }) {
  return (
    <div className="py-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-bold tabular-nums w-5 text-right shrink-0"
              style={{ color: 'var(--color-muted)' }}>{index}.</span>
        <span className="font-semibold" style={{ color: 'var(--color-text)' }}>{mission.node}</span>
        <Badge variant="accent">{mission.game_mode}</Badge>
      </div>
      <ul className="ml-7 space-y-1">
        {mission.parts.map((p) => (
          <li key={p} className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-muted)' }}>
            <ChevronRight className="size-3 shrink-0" style={{ color: 'var(--color-border)' }} />
            {p}
          </li>
        ))}
      </ul>
    </div>
  )
}

function CollapsibleCard({ icon, title, count, children }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-6 py-4 text-sm font-medium text-left transition-colors"
        style={{ color: 'var(--color-text)' }}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--color-surface2)'}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
      >
        <span style={{ color: 'var(--color-muted)' }}>{icon}</span>
        <span className="flex-1">{title}</span>
        <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
              style={{ background: 'var(--color-surface2)', color: 'var(--color-muted)', border: '1px solid var(--color-border)' }}>
          {count}
        </span>
        <ChevronDown className="size-4 transition-transform shrink-0"
                     style={{ color: 'var(--color-muted)', transform: open ? 'rotate(180deg)' : 'none' }} />
      </button>
      {open && (
        <div className="px-6 pb-5 pt-0" style={{ borderTop: '1px solid var(--color-border)' }}>
          <div className="pt-4">{children}</div>
        </div>
      )}
    </div>
  )
}

function ItemGrid({ items }) {
  return (
    <ul className="columns-2 gap-6 text-sm space-y-1.5" style={{ color: 'var(--color-muted)' }}>
      {items.map((x) => (
        <li key={x} className="break-inside-avoid flex items-center gap-2">
          <span className="size-1 rounded-full shrink-0 inline-block"
                style={{ background: 'var(--color-border)' }} />
          {x}
        </li>
      ))}
    </ul>
  )
}
