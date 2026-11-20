'use client'

import { Loader2, Mic, MicOff } from 'lucide-react'
import { LANG_LABEL, type Lang } from '@/services/api'

export type TalkState = 'connecting' | 'listening' | 'thinking' | 'speaking' | 'muted' | 'idle'

const LABELS: Record<Lang, Record<TalkState, string>> = {
  'hi-IN': { connecting: 'जुड़ रहे हैं…', listening: 'बोलिए, मैं सुन रही हूँ', thinking: 'सोच रही हूँ…', speaking: 'बोल रही हूँ', muted: 'माइक बंद है', idle: 'तैयार' },
  'kn-IN': { connecting: 'ಸಂಪರ್ಕಿಸುತ್ತಿದೆ…', listening: 'ಮಾತನಾಡಿ, ಕೇಳುತ್ತಿದ್ದೇನೆ', thinking: 'ಯೋಚಿಸುತ್ತಿದ್ದೇನೆ…', speaking: 'ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ', muted: 'ಮೈಕ್ ಆಫ್', idle: 'ಸಿದ್ಧ' },
  'en-IN': { connecting: 'Connecting…', listening: 'Speak, I am listening', thinking: 'Thinking…', speaking: 'Speaking', muted: 'Mic is off', idle: 'Ready' },
}

const STYLE: Record<TalkState, string> = {
  connecting: 'bg-muted text-muted-foreground',
  idle: 'bg-primary text-black',
  listening: 'bg-primary text-black shadow-[0_0_0_10px_hsl(var(--primary)/0.2)]',
  thinking: 'bg-amber-400 text-black animate-pulse',
  speaking: 'bg-emerald-400 text-black shadow-[0_0_0_10px_rgba(52,211,153,0.25)]',
  muted: 'bg-destructive text-white',
}

export function TalkButton({ state, lang, onToggle, disabled }: { state: TalkState; lang: Lang; onToggle: () => void; disabled?: boolean }) {
  const busy = state === 'connecting' || state === 'thinking'
  return (
    <div className="flex flex-col items-center gap-3">
      <button
        type="button"
        onClick={onToggle}
        disabled={disabled}
        aria-pressed={state === 'muted'}
        aria-label={state === 'muted' ? 'Unmute microphone' : 'Mute microphone'}
        className={`flex h-36 w-36 items-center justify-center rounded-full transition-all duration-300 focus-visible:outline focus-visible:outline-4 focus-visible:outline-offset-4 focus-visible:outline-white sm:h-44 sm:w-44 ${STYLE[state]}`}
      >
        {busy ? <Loader2 className="h-14 w-14 animate-spin" aria-hidden /> : state === 'muted' ? <MicOff className="h-14 w-14" aria-hidden /> : <Mic className="h-14 w-14" aria-hidden />}
      </button>
      <p className="min-h-7 text-center text-lg font-semibold" role="status" aria-live="polite">{LABELS[lang][state]}</p>
    </div>
  )
}

export function LanguagePill({ lang, onChange, disabled, swapping }: { lang: Lang; onChange: (l: Lang) => void; disabled?: boolean; swapping?: boolean }) {
  return (
    <div role="radiogroup" aria-label="Language" className="inline-flex items-center rounded-full border border-border bg-card/70 p-1">
      {(Object.keys(LANG_LABEL) as Lang[]).map((l) => (
        <button
          key={l}
          type="button"
          role="radio"
          aria-checked={lang === l}
          disabled={disabled || swapping}
          onClick={() => l !== lang && onChange(l)}
          className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-60 ${lang === l ? 'bg-primary text-black' : 'text-muted-foreground hover:text-foreground'}`}
        >
          {LANG_LABEL[l]}
        </button>
      ))}
      {swapping ? <Loader2 className="mx-2 h-4 w-4 animate-spin text-primary" aria-label="Switching language" /> : null}
    </div>
  )
}

export function ElderToggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} className="h-5 w-5 accent-[hsl(var(--primary))]" />
      <span>Elder mode <span className="text-xs text-muted-foreground">(bigger text, slower voice)</span></span>
    </label>
  )
}
