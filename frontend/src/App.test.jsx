import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.jsx'

function jsonResponse(body, ok = true, status = ok ? 200 : 400) {
  return Promise.resolve({
    ok,
    status,
    json: () => Promise.resolve(body),
  })
}

beforeEach(() => {
  localStorage.clear()
  global.fetch = vi.fn()
})

describe('App', () => {
  it('renders the form', () => {
    render(<App />)
    expect(screen.getByPlaceholderText(/692f1267db467ef12005e8f7/)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Caliban Prime/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Plan route/i })).toBeInTheDocument()
  })

  it('submits the wishlist and renders the resulting missions', async () => {
    global.fetch.mockReturnValue(jsonResponse({
      missing_equipment: 1,
      non_prime: [{
        node: 'Venus - Fossa', game_mode: 'Assassination',
        parts: ['Rhino Chassis Blueprint'], part_runs: {},
      }],
      non_prime_uncovered: [], prime: [], prime_part_count: 0,
      tiers: [], vaulted_equipment: [], vaulted_part_count: 0,
      vaulted_crackable: [], no_mission_source: [], no_part_source: {},
      special_source: {}, equipment_prerequisites: {}, images: {}, item_types: {},
      refinement: 'Intact', squad_radiant: false, total_minutes: 18,
      event_source: {}, active_fissures: {}, baro: null,
      daily_deal: null, market_prices: {}, buy_vs_farm: [],
      missing_equipment_names: ['Rhino'], resource_needs: [], credits_needed: null,
      partial_inventory: false,
    }))

    const user = userEvent.setup()
    render(<App />)

    await user.type(screen.getByPlaceholderText(/Caliban Prime/), 'Rhino')
    await user.click(screen.getByRole('button', { name: /Plan route/i }))

    await waitFor(() => expect(screen.getByText('Venus - Fossa')).toBeInTheDocument())
    expect(global.fetch).toHaveBeenCalledWith('/api/route', expect.objectContaining({
      method: 'POST',
    }))
    // Not necessarily call[0]: the wishlist textarea's autocomplete fires its
    // own debounced GET /api/items while the user types, which can land
    // before or after this POST depending on timing -- find the route call
    // by URL instead of assuming position.
    const [, options] = global.fetch.mock.calls.find(([url]) => url === '/api/route')
    const body = JSON.parse(options.body)
    expect(body.wishlist).toEqual(['Rhino'])
    expect(screen.getByText('Rhino Chassis Blueprint')).toBeInTheDocument()
    expect(screen.queryByText(/Using public profile only/)).not.toBeInTheDocument()
  })

  it('shows the server error message on a failed request', async () => {
    global.fetch.mockReturnValue(jsonResponse(
      { detail: 'Provide an Account ID, an inventory, or a wishlist.' }, false, 400))

    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: /Plan route/i }))

    await waitFor(() => expect(
      screen.getByText('Provide an Account ID, an inventory, or a wishlist.')
    ).toBeInTheDocument())
  })

  it('shows the partial-inventory banner when the API flags it', async () => {
    global.fetch.mockReturnValue(jsonResponse({
      missing_equipment: 1, non_prime: [], non_prime_uncovered: [],
      prime: [], prime_part_count: 0, tiers: [], vaulted_equipment: [],
      vaulted_part_count: 0, vaulted_crackable: [], no_mission_source: [],
      no_part_source: {}, special_source: {}, equipment_prerequisites: {},
      images: {}, item_types: {}, refinement: 'Intact', squad_radiant: false,
      total_minutes: null, event_source: {}, active_fissures: {}, baro: null,
      daily_deal: null, market_prices: {}, buy_vs_farm: [],
      missing_equipment_names: ['Rhino'], resource_needs: [], credits_needed: null,
      partial_inventory: true,
    }))

    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByPlaceholderText(/692f1267db467ef12005e8f7/), 'a'.repeat(24))
    await user.click(screen.getByRole('button', { name: /Plan route/i }))

    await waitFor(() => expect(
      screen.getByText(/Using public profile only/)
    ).toBeInTheDocument())
  })

  it('renders the priority-actions digest above the results', async () => {
    global.fetch.mockReturnValue(jsonResponse({
      missing_equipment: 1, non_prime: [], non_prime_uncovered: [],
      prime: [], prime_part_count: 0, tiers: [], vaulted_equipment: [],
      vaulted_part_count: 0, vaulted_crackable: [], no_mission_source: [],
      no_part_source: {}, special_source: {}, equipment_prerequisites: {},
      images: {}, item_types: {}, refinement: 'Intact', squad_radiant: false,
      total_minutes: null, event_source: {}, active_fissures: {}, baro: null,
      daily_deal: null, market_prices: {}, buy_vs_farm: [],
      missing_equipment_names: ['Rhino'], resource_needs: [], credits_needed: null,
      partial_inventory: false,
      priority_actions: [
        { urgency: 'now', title: "Darvo's Daily Deal: Rhino Prime",
          detail: '50% off — one day only.', expiry: null },
        { urgency: 'squad', title: '1 endless mode(s) in this route reward teamwork',
          detail: 'Disruption — a full squad clears rotations faster.', expiry: null },
      ],
    }))

    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByPlaceholderText(/Caliban Prime/), 'Rhino')
    await user.click(screen.getByRole('button', { name: /Plan route/i }))

    await waitFor(() => expect(screen.getByText('What to do first')).toBeInTheDocument())
    expect(screen.getByText(/Darvo's Daily Deal/)).toBeInTheDocument()
    expect(screen.getByText('NOW')).toBeInTheDocument()
    expect(screen.getByText('SQUAD')).toBeInTheDocument()
  })

  it('formats a priority-action expiry as a readable date, not a raw ISO string', async () => {
    const isoExpiry = '2026-07-12T18:00:00.000Z'
    global.fetch.mockReturnValue(jsonResponse({
      missing_equipment: 1, non_prime: [], non_prime_uncovered: [],
      prime: [], prime_part_count: 0, tiers: [], vaulted_equipment: [],
      vaulted_part_count: 0, vaulted_crackable: [], no_mission_source: [],
      no_part_source: {}, special_source: {}, equipment_prerequisites: {},
      images: {}, item_types: {}, refinement: 'Intact', squad_radiant: false,
      total_minutes: null, event_source: {}, active_fissures: {}, baro: null,
      daily_deal: null, market_prices: {}, buy_vs_farm: [],
      missing_equipment_names: ['Rhino'], resource_needs: [], credits_needed: null,
      partial_inventory: false,
      priority_actions: [
        { urgency: 'now', title: "Darvo's Daily Deal: Rhino Prime",
          detail: '50% off — one day only.', expiry: isoExpiry },
      ],
    }))

    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByPlaceholderText(/Caliban Prime/), 'Rhino')
    await user.click(screen.getByRole('button', { name: /Plan route/i }))

    await waitFor(() => expect(screen.getByText('What to do first')).toBeInTheDocument())
    expect(screen.queryByText(new RegExp(isoExpiry))).not.toBeInTheDocument()
    expect(screen.getByText(new RegExp(new Date(isoExpiry).toLocaleString().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))).toBeInTheDocument()
  })

  it('Refresh re-submits the same request and replaces the result', async () => {
    const firstResponse = {
      missing_equipment: 1,
      non_prime: [{
        node: 'Venus - Fossa', game_mode: 'Assassination',
        parts: ['Rhino Chassis Blueprint'], part_runs: {},
      }],
      non_prime_uncovered: [], prime: [], prime_part_count: 0,
      tiers: [], vaulted_equipment: [], vaulted_part_count: 0,
      vaulted_crackable: [], no_mission_source: [], no_part_source: {},
      special_source: {}, equipment_prerequisites: {}, images: {}, item_types: {},
      refinement: 'Intact', squad_radiant: false, total_minutes: 18,
      event_source: {}, active_fissures: {}, baro: null,
      daily_deal: null, market_prices: {}, buy_vs_farm: [],
      missing_equipment_names: ['Rhino'], resource_needs: [], credits_needed: null,
      partial_inventory: false,
    }
    // After collecting the Chassis (a fresh inventory sync would drop it),
    // the second /api/route response no longer lists it as needed.
    const secondResponse = {
      ...firstResponse,
      non_prime: [{
        node: 'Venus - Fossa', game_mode: 'Assassination',
        parts: [], part_runs: {},
      }],
    }
    // Keyed by URL, not call order: the wishlist textarea's autocomplete
    // fires its own debounced GET /api/items that can race the route POST.
    let routeCalls = 0
    global.fetch.mockImplementation((url) => {
      if (url === '/api/route') {
        routeCalls += 1
        return jsonResponse(routeCalls === 1 ? firstResponse : secondResponse)
      }
      return jsonResponse({ items: [] })
    })

    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByPlaceholderText(/Caliban Prime/), 'Rhino')
    await user.click(screen.getByRole('button', { name: /Plan route/i }))
    await waitFor(() => expect(screen.getByText('Rhino Chassis Blueprint')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /Refresh/i }))
    await waitFor(() => expect(screen.queryByText('Rhino Chassis Blueprint')).not.toBeInTheDocument())

    expect(routeCalls).toBe(2)
  })
})
