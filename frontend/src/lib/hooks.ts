import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import * as api from './api'
import { TERMINAL, type ProgressEvent } from './types'

export const useHealth = () => useQuery({ queryKey: ['health'], queryFn: api.getHealth, retry: false, staleTime: 30_000 })

export function useStatus(runId: string) {
  return useQuery({
    queryKey: ['status', runId], queryFn: () => api.getStatus(runId), retry: 1, enabled: !!runId,
    refetchInterval: (q) => (q.state.status === 'error' || !q.state.data || TERMINAL.includes(q.state.data.status) ? false : 1200),
  })
}
/** Polls events with the `after` cursor and accumulates them (ascending, de-duplicated). */
export function useEvents(runId: string, active: boolean) {
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const cursor = useRef(0)
  useEffect(() => { setEvents([]); cursor.current = 0; setError(null) }, [runId])
  useEffect(() => {
    let stop = false
    const tick = async () => {
      try {
        const batch = await api.getEvents(runId, cursor.current)
        if (stop) return
        if (batch.length) {
          cursor.current = Math.max(cursor.current, ...batch.map((e) => e.sequence))
          setEvents((prev) => { const seen = new Set(prev.map((e) => e.sequence)); return [...prev, ...batch.filter((e) => !seen.has(e.sequence))].sort((a, b) => a.sequence - b.sequence) })
        }
        setError(null)
      } catch (e) { if (!stop) setError((e as Error).message) }
    }
    void tick()
    if (!active) return () => { stop = true }
    const t = setInterval(tick, 1200)
    return () => { stop = true; clearInterval(t) }
  }, [runId, active])
  return { events, error }
}
export const useResult = (runId: string, enabled: boolean) =>
  useQuery({ queryKey: ['result', runId], queryFn: () => api.getResult(runId), enabled, retry: false })
export const useEvidence = (runId: string, enabled: boolean) =>
  useQuery({ queryKey: ['evidence', runId], queryFn: () => api.getEvidence(runId), enabled, retry: false })
