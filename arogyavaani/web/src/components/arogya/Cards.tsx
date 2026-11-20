'use client'

import { CalendarPlus, MapPin, ShieldAlert, Volume2 } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import type { Booking, Doctor } from '@/hooks/useEvents'

const LANG_NAME: Record<string, string> = { kn: 'ಕನ್ನಡ', hi: 'हिन्दी', en: 'English', ta: 'தமிழ்', te: 'తెలుగు', ml: 'മലയാളം' }
const STAGES = ['BEFORE', 'DURING', 'ACTION', 'CONFIRM', 'AFTER'] as const

export function StageBar({ stage }: { stage: string }) {
  const idx = STAGES.indexOf(stage as (typeof STAGES)[number])
  return (
    <ol className="flex items-center gap-1" aria-label="Journey stage">
      {STAGES.map((s, i) => (
        <li
          key={s}
          aria-current={i === idx ? 'step' : undefined}
          className={`flex-1 rounded-full px-2 py-1 text-center text-[10px] font-semibold uppercase tracking-wide transition-colors ${
            stage === 'ESCALATED' ? 'bg-red-500/20 text-red-300' : i === idx ? 'bg-primary text-black' : i < idx ? 'bg-primary/25 text-primary' : 'bg-muted text-muted-foreground'
          }`}
        >
          {s}
        </li>
      ))}
    </ol>
  )
}

export function RedFlagBanner({ reason }: { reason: string }) {
  return (
    <div role="alert" className="flex animate-fade-up items-center gap-3 rounded-xl border border-red-500 bg-red-500/20 p-4 text-red-100">
      <ShieldAlert className="h-8 w-8 shrink-0" aria-hidden />
      <div>
        <p className="text-lg font-bold">Possible emergency: call 108 now</p>
        <p className="text-sm opacity-90">Booking is paused ({reason.replace(/_/g, ' ')}). A nurse has been alerted and can speak through the agent.</p>
      </div>
    </div>
  )
}

export function DoctorCards({ doctors }: { doctors: Doctor[] }) {
  if (!doctors.length) return null
  return (
    <section aria-label="Recommended doctors" className="grid gap-2">
      {doctors.map((d, i) => (
        <article key={d.id} className="animate-fade-up rounded-xl border border-border bg-card/60 p-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold">
                {i === 0 ? '★ ' : ''}{d.name}
              </h3>
              <p className="text-xs capitalize text-muted-foreground">{d.specialty} · {d.clinic}</p>
            </div>
            <span className="shrink-0 text-sm font-semibold tabular-nums">₹{d.fee_inr}</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {d.languages.map((l) => (
              <span key={l} className={`rounded-full px-2 py-0.5 text-[11px] ${d.language_match?.includes(l) ? 'bg-primary text-black font-semibold' : 'bg-muted text-muted-foreground'}`}>
                {LANG_NAME[l] ?? l}
              </span>
            ))}
            {d.distance_km != null ? (
              <span className="inline-flex items-center gap-0.5 text-[11px] text-muted-foreground"><MapPin className="h-3 w-3" aria-hidden />{d.distance_km} km</span>
            ) : null}
            {d.pmjay ? <span className="rounded-full border border-emerald-500/50 px-2 py-0.5 text-[11px] text-emerald-300">PM-JAY</span> : null}
            <span className="ml-auto text-[11px] text-muted-foreground">★ {d.rating}</span>
          </div>
        </article>
      ))}
    </section>
  )
}

export function AppointmentCard({
  booking, doctor, voiceNote, ics,
}: { booking: Booking; doctor: Doctor | null; voiceNote: string | null; ics: string | null }) {
  return (
    <section aria-label="Appointment confirmed" className="animate-fade-up rounded-2xl border border-emerald-500/50 bg-emerald-500/10 p-4">
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-300">Appointment confirmed</p>
          <h3 className="mt-1 text-lg font-bold">{doctor?.name ?? booking.doctor_id}</h3>
          <p className="text-sm text-muted-foreground">{doctor?.clinic}</p>
          <p className="mt-2 text-xl font-semibold tabular-nums">{booking.date} · {booking.time}</p>
          <p className="mt-1 text-xs text-muted-foreground">Booking ID <span className="font-mono text-foreground">{booking.booking_id}</span></p>
        </div>
        <div className="rounded-lg bg-white p-2" aria-label={`QR code for booking ${booking.booking_id}`}>
          <QRCodeSVG value={`arogyavaani:${booking.booking_id}`} size={84} />
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {ics ? (
          <a href={ics} download className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted">
            <CalendarPlus className="h-3.5 w-3.5" aria-hidden /> Add to calendar
          </a>
        ) : null}
        {voiceNote ? (
          <div className="flex items-center gap-2 rounded-lg border border-border px-2 py-1">
            <Volume2 className="h-3.5 w-3.5 text-primary" aria-hidden />
            {/* biome-ignore lint/a11y/useMediaCaption: short generated voice note, text confirmation is in the inbox */}
            <audio controls src={voiceNote} className="h-7 max-w-[11rem]" aria-label="Murf voice note" />
          </div>
        ) : null}
      </div>
    </section>
  )
}
