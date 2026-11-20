'use client'

import { Inbox, Phone, PhoneOff, Settings2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { demo, getInbox, type InboxMessage } from '@/services/api'

export type IncomingCallInfo = {
  followup_id: number
  patient_id: string
  kind: 'reminder' | 'feedback'
  doctor: string
  patient_name: string
  lang: string
}

/** Two-tone phone ring generated with WebAudio (no asset needed). Browsers need a prior user gesture to play. */
function useRingtone(active: boolean) {
  const ctxRef = useRef<AudioContext | null>(null)
  useEffect(() => {
    if (!active) return
    let stopped = false
    const ctx = new AudioContext()
    ctxRef.current = ctx
    const ring = () => {
      if (stopped) return
      const now = ctx.currentTime
      for (const [i, f] of [440, 480, 440, 480].entries()) {
        const o = ctx.createOscillator()
        const g = ctx.createGain()
        o.frequency.value = f
        g.gain.setValueAtTime(0.0001, now + i * 0.22)
        g.gain.exponentialRampToValueAtTime(0.15, now + i * 0.22 + 0.02)
        g.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.22 + 0.2)
        o.connect(g).connect(ctx.destination)
        o.start(now + i * 0.22)
        o.stop(now + i * 0.22 + 0.21)
      }
    }
    ring()
    const t = setInterval(ring, 2200)
    return () => {
      stopped = true
      clearInterval(t)
      ctx.close().catch(() => {})
    }
  }, [active])
}

export function IncomingCall({ call, onAccept, onDecline }: { call: IncomingCallInfo; onAccept: () => void; onDecline: () => void }) {
  useRingtone(true)
  const title = call.kind === 'reminder' ? 'Appointment reminder' : 'How was your visit?'
  return (
    <div role="alertdialog" aria-label="Incoming call from ArogyaVaani" className="fixed inset-0 z-50 flex flex-col items-center justify-between bg-black/90 px-6 py-16 text-center backdrop-blur">
      <div>
        <p className="text-sm uppercase tracking-widest text-muted-foreground">Incoming call</p>
        <h2 className="mt-3 text-3xl font-bold">ArogyaVaani</h2>
        <p className="mt-2 text-lg text-primary">{title}</p>
        <p className="mt-1 text-sm text-muted-foreground">{call.doctor}</p>
      </div>
      <div className="relative flex h-28 w-28 items-center justify-center">
        <span className="absolute h-full w-full animate-ping rounded-full bg-primary/30" />
        <span className="relative flex h-24 w-24 items-center justify-center rounded-full bg-primary text-4xl font-bold text-black">आ</span>
      </div>
      <div className="flex gap-16">
        <button type="button" onClick={onDecline} aria-label="Decline call" className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive text-white">
          <PhoneOff className="h-7 w-7" />
        </button>
        <button type="button" onClick={onAccept} aria-label="Accept call" className="flex h-16 w-16 animate-bounce items-center justify-center rounded-full bg-emerald-500 text-white">
          <Phone className="h-7 w-7" />
        </button>
      </div>
    </div>
  )
}

export function InboxDrawer({ patientId, refreshKey }: { patientId: string; refreshKey: number }) {
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<InboxMessage[]>([])
  useEffect(() => {
    if (open || refreshKey) getInbox(patientId).then(setMsgs).catch(() => {})
  }, [open, patientId, refreshKey])
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} aria-label={`Messages, ${msgs.length}`} className="relative inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted">
        <Inbox className="h-4 w-4" aria-hidden /> Messages
        {msgs.length > 0 ? <span className="rounded-full bg-primary px-1.5 text-[10px] font-bold text-black">{msgs.length}</span> : null}
      </button>
      {open ? (
        <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-sm flex-col border-l border-border bg-background shadow-2xl" aria-label="Inbox">
          <div className="flex h-14 items-center justify-between border-b border-border px-4">
            <h2 className="font-semibold">Inbox (WhatsApp / SMS)</h2>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close inbox"><X className="h-5 w-5" /></button>
          </div>
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {msgs.length === 0 ? <p className="text-sm text-muted-foreground">No messages yet.</p> : null}
            {msgs.map((m) => (
              <article key={m.id} className="rounded-xl border border-border bg-card p-3">
                <div className="mb-1 flex items-center justify-between text-[11px] uppercase tracking-wide text-muted-foreground">
                  <span>to {m.recipient}</span><span>{m.channel}{m.delivered ? '' : ' · fallback'}</span>
                </div>
                <p className="whitespace-pre-wrap text-sm leading-6">{m.text}</p>
                {m.media_url ? (
                  // biome-ignore lint/a11y/useMediaCaption: generated voice note
                  <audio controls src={m.media_url} className="mt-2 h-8 w-full" aria-label="Voice note" />
                ) : null}
                {m.ics_url ? <a className="mt-2 inline-block text-xs text-primary underline" href={m.ics_url} download>Add to calendar (.ics)</a> : null}
              </article>
            ))}
          </div>
        </aside>
      ) : null}
    </>
  )
}

/** Visible only with ?demo=1 */
export function DemoDrawer() {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  const run = async (label: string, fn: () => Promise<unknown>) => {
    setNote(`${label}…`)
    try {
      await fn()
      setNote(`${label}: done`)
    } catch (e) {
      setNote(`${label}: ${(e as Error).message}`)
    }
  }
  return (
    <div className="fixed bottom-16 left-3 z-40">
      {open ? (
        <div className="mb-2 w-64 rounded-xl border border-border bg-card p-3 shadow-xl">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Demo controls</p>
          <div className="grid gap-2">
            <button type="button" className="rounded-lg bg-muted px-3 py-2 text-left text-sm hover:bg-muted/70" onClick={() => run('Force slot conflict', demo.forceConflict)}>Force slot conflict (next hold)</button>
            <button type="button" className="rounded-lg bg-muted px-3 py-2 text-left text-sm hover:bg-muted/70" onClick={() => run('Fast-forward', demo.fastForward)}>Fast-forward to reminder call</button>
            <button type="button" className="rounded-lg bg-muted px-3 py-2 text-left text-sm hover:bg-muted/70" onClick={() => run('Seed Lakshmi', demo.seed)}>Seed Lakshmi profile</button>
            <button type="button" className="rounded-lg bg-destructive/20 px-3 py-2 text-left text-sm text-red-200 hover:bg-destructive/30" onClick={() => run('Reset demo data', demo.reset)}>Reset demo data</button>
          </div>
          {note ? <p className="mt-2 text-xs text-muted-foreground" role="status">{note}</p> : null}
        </div>
      ) : null}
      <button type="button" onClick={() => setOpen((o) => !o)} aria-label="Demo controls" className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-card shadow-lg">
        <Settings2 className="h-5 w-5" />
      </button>
    </div>
  )
}
