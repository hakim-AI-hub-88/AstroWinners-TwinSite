import { afterEach, describe, expect, it, vi } from 'vitest'
import { getCatalog, getRecords } from '@/lib/api'

const respond = (status: number, body: unknown) => vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

afterEach(() => vi.unstubAllGlobals())

describe('data endpoint demo fallback', () => {
  it('uses live data when the API answers', async () => {
    vi.stubGlobal('fetch', respond(200, { items: [{ dataset_id: 'earth-zagora-draa', body: 'Earth', data_status: 'measured' }] }))
    const r = await getCatalog()
    expect(r.demo).toBe(false)
    expect(r.data[0].dataset_id).toBe('earth-zagora-draa')
  })
  it('falls back to labelled demo data only when the API is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    const r = await getCatalog()
    expect(r.demo).toBe(true)
    expect(r.note).toMatch(/DEMO/)
  })
  it('treats a bare proxy 502 (backend down) as unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Bad Gateway', { status: 502 })))
    expect((await getCatalog()).demo).toBe(true)
  })
  it('falls back for a 501 reserved endpoint', async () => {
    vi.stubGlobal('fetch', respond(501, { error: { code: 'NOT_IMPLEMENTED', message: 'reserved' } }))
    expect((await getCatalog()).demo).toBe(true)
  })
  it.each([404, 422, 500])('never masks a real %i error with demo data', async (status) => {
    vi.stubGlobal('fetch', respond(status, { error: { code: 'X', message: 'real error' } }))
    await expect(getRecords('nope', 'cleaned')).rejects.toMatchObject({ status })
  })
})
