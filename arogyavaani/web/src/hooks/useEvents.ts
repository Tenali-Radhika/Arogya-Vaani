'use client'

import { useEffect, useRef, useState } from 'react'
import { eventsUrl } from '@/services/api'

export type AgentEvent = {
  type: string
  ts: number
  session_id: string
  [key: string]: unknown
}

export type Doctor = {
  id: string
  name: string
  specialty: string
  clinic: string
  area: string
  languages: string[]
  fee_inr: number
  pmjay: boolean
  rating: number
  distance_km?: number | null
  language_match?: string[]
  why?: string
}

export type Booking = { booking_id: string; doctor_id: string; date: string; time: string; status: string }

/** Subscribe to /ws/events/{channelId} with auto-reconnect. Replays recent events on connect. */
export function useEvents(channelId: string | null, onEvent?: (e: AgentEvent) => void) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [connected, setConnected] = useState(false)
  const cb = useRef(onEvent)
  cb.current = onEvent

  useEffect(() => {
    if (!channelId) return
    let ws: WebSocket | null = null
    let closed = false
    let retry = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    const seen = new Set<string>()

    const connect = () => {
      ws = new WebSocket(eventsUrl(channelId))
      ws.onopen = () => {
        retry = 0
        setConnected(true)
      }
      ws.onmessage = (m) => {
        try {
          const e = JSON.parse(m.data) as AgentEvent
          if (e.type === 'ping') return
          const key = `${e.ts}|${e.type}|${e.tool ?? ''}|${e.session_id}`
          if (seen.has(key)) return
          seen.add(key)
          setEvents((prev) => [...prev, e].slice(-300))
          cb.current?.(e)
        } catch {}
      }
      ws.onclose = () => {
        setConnected(false)
        if (!closed) timer = setTimeout(connect, Math.min(4000, 400 * 2 ** retry++))
      }
      ws.onerror = () => ws?.close()
    }
    connect()
    return () => {
      closed = true
      if (timer) clearTimeout(timer)
      ws?.close()
    }
  }, [channelId])

  return { events, connected }
}

export type DerivedState = {
  stage: string
  doctors: Doctor[]
  appointment: { booking: Booking; doctor: Doctor | null } | null
  redFlag: { reason: string } | null
  lastSwapMs: number | null
  swapping: boolean
  voiceNote: string | null
  ics: string | null
  p50: number | null
  feedback: number | null
  nurseLines: string[]
}

export function deriveState(events: AgentEvent[]): DerivedState {
  const s: DerivedState = {
    stage: 'BEFORE', doctors: [], appointment: null, redFlag: null, lastSwapMs: null, swapping: false,
    voiceNote: null, ics: null, p50: null, feedback: null, nurseLines: [],
  }
  for (const e of events) {
    switch (e.type) {
      case 'stage': s.stage = String(e.stage); break
      case 'doctors': s.doctors = (e.doctors as Doctor[]) ?? []; break
      case 'appointment': s.appointment = { booking: e.booking as Booking, doctor: (e.doctor as Doctor) ?? null }; break
      case 'red_flag': s.redFlag = { reason: String(e.reason) }; break
      case 'escalation_resolved': s.redFlag = null; break
      case 'language_swap':
        if (e.phase === 'start') s.swapping = true
        else { s.swapping = false; s.lastSwapMs = Number(e.ms) }
        break
      case 'inbox': s.voiceNote = (e.voice_note as string) ?? s.voiceNote; s.ics = (e.ics as string) ?? s.ics; break
      case 'turn_metrics': s.p50 = Number(e.p50_ms) || s.p50; break
      case 'feedback': s.feedback = Number(e.rating); break
      case 'nurse_speak': s.nurseLines.push(String(e.text)); break
    }
  }
  return s
}
