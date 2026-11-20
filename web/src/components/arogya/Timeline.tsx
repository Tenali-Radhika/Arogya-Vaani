'use client'

import {
  BookOpen, CalendarCheck, CheckCircle2, Languages, Loader2, Lock, Phone, Search, Send, ShieldAlert,
  Stethoscope, Star, UserRound, Wrench, XCircle, Mic2,
} from 'lucide-react'
import { useEffect, useMemo, useRef } from 'react'
import type { AgentEvent } from '@/hooks/useEvents'

const ICONS: Record<string, typeof Wrench> = {
  triage_symptoms: Stethoscope, search_doctors: Search, check_availability: CalendarCheck, hold_slot: Lock,
  confirm_booking: CheckCircle2, cancel_booking: XCircle, send_confirmation: Send, generate_voice_note: Mic2,
  schedule_followup: Phone, record_feedback: Star, escalate_to_human: ShieldAlert, set_language: Languages,
  get_patient_profile: UserRound, save_patient_profile: UserRound, search_knowledge: BookOpen, geocode_area: Search,
}

type Row =
  | { kind: 'tool'; id: string; tool: string; summary?: string; ms?: number; ok?: boolean; pending: boolean; args?: unknown }
  | { kind: 'note'; id: string; tone: 'info' | 'warn' | 'danger' | 'good'; text: string }

export function buildRows(events: AgentEvent[]): Row[] {
  const rows: Row[] = []
  for (const e of events) {
    const id = `${e.ts}-${e.type}-${e.tool ?? ''}`
    if (e.type === 'tool_start') {
      rows.push({ kind: 'tool', id, tool: String(e.tool), pending: true, args: e.args })
    } else if (e.type === 'tool_end') {
      const i = [...rows].reverse().findIndex((r) => r.kind === 'tool' && r.pending && r.tool === e.tool)
      const row: Row = { kind: 'tool', id, tool: String(e.tool), summary: String(e.summary ?? ''), ms: Number(e.ms), ok: Boolean(e.ok), pending: false, args: e.args }
      if (i >= 0) rows[rows.length - 1 - i] = row
      else rows.push(row)
    } else if (e.type === 'language_swap' && e.phase === 'done') {
      rows.push({ kind: 'note', id, tone: 'good', text: `Language swap to ${e.to} in ${e.ms} ms (memory kept)` })
    } else if (e.type === 'language_swap' && e.phase === 'start') {
      rows.push({ kind: 'note', id, tone: 'info', text: `Switching ${e.from} to ${e.to}: leave + re-join` })
    } else if (e.type === 'red_flag') {
      rows.push({ kind: 'note', id, tone: 'danger', text: `RED FLAG (${e.reason}): booking stopped, nurse alerted, call 108` })
    } else if (e.type === 'nurse_speak') {
      rows.push({ kind: 'note', id, tone: 'warn', text: `Nurse spoke through the agent: "${e.text}"` })
    } else if (e.type === 'feedback') {
      rows.push({ kind: 'note', id, tone: 'good', text: `Voice rating ${e.rating}/5 recorded` })
    } else if (e.type === 'incoming_call') {
      rows.push({ kind: 'note', id, tone: 'info', text: `Agent is calling the patient (${e.kind} reminder)` })
    } else if (e.type === 'warning' || e.type === 'error') {
      rows.push({ kind: 'note', id, tone: 'warn', text: String(e.text) })
    }
  }
  return rows
}

const TONE = {
  info: 'border-primary/40 bg-primary/10 text-foreground',
  good: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200',
  warn: 'border-amber-500/40 bg-amber-500/10 text-amber-200',
  danger: 'border-red-500/60 bg-red-500/15 text-red-200',
}

export function ActionTimeline({ events }: { events: AgentEvent[] }) {
  const rows = useMemo(() => buildRows(events), [events])
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  })
  return (
    <section aria-label="Agent actions" className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-border bg-card/20">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
        <div>
          <h2 className="text-sm font-semibold">Agent actions</h2>
          <p className="text-xs text-muted-foreground">Every tool the agent runs, live</p>
        </div>
        <span className="rounded-full bg-primary/15 px-2 py-0.5 text-xs text-primary">{rows.filter((r) => r.kind === 'tool').length} calls</span>
      </div>
      <div ref={ref} className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3">
        {rows.length === 0 ? (
          <p className="m-auto text-center text-sm text-muted-foreground">Tool calls appear here as the agent works.</p>
        ) : (
          rows.map((r) =>
            r.kind === 'note' ? (
              <div key={r.id} className={`animate-fade-up rounded-lg border px-3 py-2 text-sm ${TONE[r.tone]}`} role={r.tone === 'danger' ? 'alert' : undefined}>
                {r.text}
              </div>
            ) : (
              <ToolCard key={r.id} row={r} />
            ),
          )
        )}
      </div>
    </section>
  )
}

function ToolCard({ row }: { row: Extract<Row, { kind: 'tool' }> }) {
  const Icon = ICONS[row.tool] ?? Wrench
  const border = row.pending ? 'border-border' : row.ok ? 'border-emerald-500/40' : 'border-red-500/50'
  return (
    <div className={`animate-fade-up flex items-start gap-3 rounded-lg border bg-card/60 px-3 py-2 ${border}`}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <code className="truncate text-xs font-semibold">{row.tool}</code>
          {row.pending ? (
            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" aria-label="running" />
          ) : (
            <>
              <span className={`ml-auto rounded px-1.5 py-0.5 text-[10px] font-medium ${row.ok ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'}`}>
                {row.ok ? 'OK' : 'ERR'}
              </span>
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground">{row.ms} ms</span>
            </>
          )}
        </div>
        <p className="mt-0.5 break-words text-xs text-muted-foreground">{row.pending ? 'running…' : row.summary}</p>
      </div>
    </div>
  )
}
