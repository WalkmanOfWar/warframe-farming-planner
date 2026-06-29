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
    <div className="max-w-3xl mx-auto px-4 py-8 pb-16">
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <Swords className="size-7 text-[var(--color-gold)]" />
          <h1 className="text-2xl font-bold text-[var(--color-gold)] tracking-wide">
            Warframe Farming Planner
          </h1>
        </div>
        <p className="text-[var(--color-muted)] text-sm">
          Plan the fewest missions to farm everything you're still missing.
        </p>
      </header>

      {/* Form */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Your profile</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-1.5">
            <Label htmlFor="account-id">
              Account ID{' '}
              <span className="text-[var(--color-muted)] font-normal">
                (24-hex <code className="text-xs bg-[var(--color-surface2)] px-1 rounded">gid</code> cookie, not username)
              </span>
            </Label>
            <Input
              id="account-id"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              placeholder="e.g. 692f1267db467ef12005e8f7"
              spellCheck={false}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="nonce">
              Nonce{' '}
              <span className="text-[var(--color-muted)] font-normal">
                (optional — full inventory incl. loose parts)
              </span>
            </Label>
            <Input
              id="nonce"
              value={nonce}
              onChange={(e) => setNonce(e.target.value)}
              placeholder="from warframe-api-helper with the game running"
              spellCheck={false}
            />
          </div>

          <div className="space-y-1.5">
            <Label>
              Inventory file{' '}
              <span className="text-[var(--color-muted)] font-normal">
                (optional — inventory.json from AlecaFrame / api-helper)
              </span>
            </Label>
            {invName ? (
              <div className="flex items-center gap-2 rounded-lg border border-[var(--color-success)]/40 bg-[var(--color-success)]/5 px-3 py-2 text-sm">
                <CheckCircle2 className="size-4 text-[var(--color-success)] shrink-0" />
                <span className="text-[var(--color-text)] flex-1 truncate">{invName}</span>
                <button
                  onClick={clearInventory}
                  className="text-[var(--color-muted)] hover:text-[var(--color-error)] transition-colors"
                >
                  <X className="size-4" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => fileRef.current?.click()}
                className={cn(
                  'flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--color-border)]',
                  'px-4 py-4 text-sm text-[var(--color-muted)] transition-colors',
                  'hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] cursor-pointer'
                )}
              >
                <Upload className="size-4" />
                Click to upload inventory.json
              </button>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="application/json,.json"
              onChange={onInventory}
              className="hidden"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="wishlist">
              Wishlist{' '}
              <span className="text-[var(--color-muted)] font-normal">
                (optional — one item per line; empty = everything masterable)
              </span>
            </Label>
            <Textarea
              id="wishlist"
              rows={3}
              value={wishlist}
              onChange={(e) => setWishlist(e.target.value)}
              placeholder={'Caliban Prime\nVolt Prime\nSibear'}
            />
          </div>

          <Button onClick={plan} disabled={loading} size="lg" className="w-full">
            {loading
              ? <><Loader2 className="size-4 animate-spin" /> Planning…</>
              : <><Crosshair className="size-4" /> Plan route</>
            }
          </Button>

          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-[var(--color-error)]/40 bg-[var(--color-error)]/5 px-3 py-2.5 text-sm text-[var(--color-error)]">
              <AlertCircle className="size-4 mt-0.5 shrink-0" />
              {error}
            </div>
          )}
        </CardContent>
      </Card>

      {result && <Results r={result} />}

      <footer className="text-center text-xs text-[var(--color-muted)] mt-8">
        Unofficial fan tool · Data from{' '}
        <a href="https://docs.warframestat.us" className="text-[var(--color-accent)] hover:underline">WFCD / warframestat</a>
        {' '}· Not affiliated with Digital Extremes
      </footer>
    </div>
  )
}

/* ── Results ───────────────────────────────────────────────── */

function Results({ r }) {
  if (!r.missing_equipment) {
    return (
      <Card className="mb-4">
        <CardContent className="pt-5 flex items-center gap-3">
          <CheckCircle2 className="size-5 text-[var(--color-success)]" />
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
        <StatCard icon={<Swords className="size-4" />}   n={r.missing_equipment}   label="missing items" />
        <StatCard icon={<MapPin className="size-4" />}   n={nonPrimeParts}          label="non-prime parts" />
        <StatCard icon={<Gem className="size-4" />}      n={r.prime.length}         label="prime parts" />
        <StatCard icon={<Lock className="size-4" />}     n={r.vaulted_part_count}   label="vaulted parts" />
      </div>

      {/* Non-prime missions */}
      {r.non_prime.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MapPin className="size-4" />
              Non-Prime — {r.non_prime.length} mission{r.non_prime.length !== 1 ? 's' : ''}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-0 pt-0">
            {r.non_prime.map((m, i) => (
              <div key={i}>
                {i > 0 && <Separator className="my-0" />}
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
            <CardTitle className="flex items-center gap-2">
              <Gem className="size-4" />
              Prime — {r.prime.length} part{r.prime.length !== 1 ? 's' : ''}
            </CardTitle>
            <p className="text-xs text-[var(--color-muted)] mt-1">
              Farm a relic's <strong className="text-[var(--color-text)]">tier</strong>, then crack it at a void fissure.
            </p>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="rounded-lg border border-[var(--color-border)] overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface2)]">
                    <th className="text-left px-3 py-2 text-[var(--color-muted)] font-medium">Part</th>
                    <th className="text-left px-3 py-2 text-[var(--color-muted)] font-medium">In-rotation relics</th>
                  </tr>
                </thead>
                <tbody>
                  {r.prime.map((p, i) => (
                    <tr key={p.part} className={cn(i > 0 && 'border-t border-[var(--color-border)]')}>
                      <td className="px-3 py-2.5 font-medium text-[var(--color-text)] align-top whitespace-nowrap pr-4">
                        {p.part}
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex flex-wrap gap-1">
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
              <div className="mt-4">
                <p className="text-xs font-semibold text-[var(--color-muted)] uppercase tracking-wider mb-2">
                  Relic tiers to farm
                </p>
                <div className="space-y-1.5">
                  {r.tiers.map((t) => (
                    <div key={t.tier} className="flex items-center gap-3 text-sm">
                      <Badge variant={TIER_VARIANT[t.tier] ?? 'default'} className="min-w-[56px] justify-center">
                        {t.tier}
                      </Badge>
                      <span className="text-[var(--color-muted)]">{t.where}</span>
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
          title={`Vaulted / not currently farmable`}
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
    <Card className="text-center py-4 px-3">
      <div className="flex justify-center mb-1 text-[var(--color-gold)]">{icon}</div>
      <div className="text-2xl font-bold text-[var(--color-gold)]">{n}</div>
      <div className="text-xs text-[var(--color-muted)] mt-0.5">{label}</div>
    </Card>
  )
}

function MissionRow({ index, mission }) {
  return (
    <div className="py-3 px-1">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-xs font-bold text-[var(--color-muted)] w-5 text-right">{index}.</span>
        <span className="font-semibold text-[var(--color-text)]">{mission.node}</span>
        <Badge variant="accent">{mission.game_mode}</Badge>
      </div>
      <ul className="ml-7 space-y-0.5">
        {mission.parts.map((p) => (
          <li key={p} className="flex items-center gap-1.5 text-sm text-[var(--color-muted)]">
            <ChevronRight className="size-3 shrink-0 text-[var(--color-border)]" />
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
    <Card>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-5 py-4 text-sm font-medium text-left text-[var(--color-text)] hover:text-[var(--color-gold)] transition-colors"
      >
        <span className="text-[var(--color-muted)]">{icon}</span>
        <span className="flex-1">{title}</span>
        <Badge variant="default" className="mr-2">{count}</Badge>
        <ChevronDown className={cn('size-4 text-[var(--color-muted)] transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <CardContent className="pt-0 border-t border-[var(--color-border)]">
          <div className="pt-3">{children}</div>
        </CardContent>
      )}
    </Card>
  )
}

function ItemGrid({ items }) {
  return (
    <ul className="columns-2 gap-4 text-sm text-[var(--color-muted)] space-y-1">
      {items.map((x) => (
        <li key={x} className="break-inside-avoid flex items-center gap-1.5">
          <span className="size-1.5 rounded-full bg-[var(--color-border)] shrink-0" />
          {x}
        </li>
      ))}
    </ul>
  )
}
