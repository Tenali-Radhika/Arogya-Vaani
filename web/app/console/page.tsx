"use client";

import { Headset, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { consoleFetch } from "@/services/api";

type Line = { role: string; text: string; lang: string };
type Sess = {
	id: string;
	patient_name: string;
	patient_id: string;
	stage: string;
	lang: string;
	live: boolean;
	escalated: boolean;
	escalation_reason: string;
	transcript: Line[];
};
type Snapshot = {
	sessions: Sess[];
	bookings: { id: string; doctor: string; date: string; time: string; patient_id: string; status: string }[];
	feedback: { id: number; booking_id: string; rating: number; comment: string }[];
};

const QUICK: Record<string, string[]> = {
	hi: ["घबराइए मत, मैं नर्स बोल रही हूँ। कृपया अभी 108 पर call कीजिए।", "क्या आप बैठ सकते हैं? आपके साथ कोई है?", "एम्बुलेंस रास्ते में है, लाइन पर बने रहिए।"],
	kn: ["ಗಾಬರಿಯಾಗಬೇಡಿ, ನಾನು ನರ್ಸ್ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. ಈಗಲೇ 108 ಕ್ಕೆ ಕರೆ ಮಾಡಿ.", "ದಯವಿಟ್ಟು ಕುಳಿತುಕೊಳ್ಳಿ. ನಿಮ್ಮ ಜೊತೆ ಯಾರಾದರೂ ಇದ್ದಾರೆಯೇ?", "ಆಂಬ್ಯುಲೆನ್ಸ್ ಬರುತ್ತಿದೆ, ಲೈನ್‌ನಲ್ಲಿ ಇರಿ."],
	en: ["Stay calm, this is the nurse. Please call 108 right now.", "Can you sit down? Is anyone with you?", "An ambulance is on the way. Please stay on the line."],
};

export default function ConsolePage() {
	const [pw, setPw] = useState("");
	const [authed, setAuthed] = useState(false);
	const [data, setData] = useState<Snapshot | null>(null);
	const [err, setErr] = useState("");

	const load = useCallback(async () => {
		try {
			setData(await consoleFetch<Snapshot>("/console/sessions", pw));
			setAuthed(true);
			setErr("");
		} catch (e) {
			setAuthed(false);
			setErr((e as Error).message);
		}
	}, [pw]);

	useEffect(() => {
		if (!authed) return;
		const t = setInterval(load, 2000);
		return () => clearInterval(t);
	}, [authed, load]);

	if (!authed) {
		return (
			<main className="flex min-h-screen items-center justify-center p-6">
				<form
					onSubmit={(e) => {
						e.preventDefault();
						load();
					}}
					className="w-full max-w-sm rounded-2xl border border-border bg-card p-6"
				>
					<h1 className="flex items-center gap-2 text-xl font-semibold"><Headset className="h-5 w-5" aria-hidden /> Nurse console</h1>
					<label className="mt-4 block text-sm" htmlFor="pw">Console password</label>
					<input id="pw" type="password" value={pw} onChange={(e) => setPw(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2" />
					{err ? <p className="mt-2 text-sm text-destructive" role="alert">{err}</p> : null}
					<button type="submit" className="mt-4 w-full rounded-lg bg-primary px-3 py-2 font-medium text-black">Open console</button>
				</form>
			</main>
		);
	}

	const open = data?.sessions.filter((s) => s.escalated) ?? [];
	return (
		<main className="mx-auto max-w-6xl space-y-6 p-4 md:p-8">
			<header className="flex items-center justify-between">
				<h1 className="flex items-center gap-2 text-2xl font-semibold"><Headset className="h-6 w-6" aria-hidden /> ArogyaVaani nurse console</h1>
				<span className={`rounded-full px-3 py-1 text-sm ${open.length ? "bg-red-500/20 text-red-200" : "bg-emerald-500/15 text-emerald-300"}`}>
					{open.length ? `${open.length} open escalation${open.length > 1 ? "s" : ""}` : "No open escalations"}
				</span>
			</header>

			<section aria-label="Sessions" className="grid gap-4 md:grid-cols-2">
				{data?.sessions.length === 0 ? <p className="text-muted-foreground">No sessions yet.</p> : null}
				{data?.sessions.map((s) => <SessionCard key={s.id} s={s} pw={pw} onChanged={load} />)}
			</section>

			<section className="grid gap-4 md:grid-cols-2" aria-label="After-visit view">
				<div className="rounded-2xl border border-border bg-card/40 p-4">
					<h2 className="mb-2 font-semibold">Bookings</h2>
					<ul className="space-y-1 text-sm">
						{data?.bookings.map((b) => (
							<li key={b.id} className="flex justify-between"><span>{b.id} · {b.doctor}</span><span className="tabular-nums text-muted-foreground">{b.date} {b.time} · {b.status}</span></li>
						))}
						{data?.bookings.length === 0 ? <li className="text-muted-foreground">None yet.</li> : null}
					</ul>
				</div>
				<div className="rounded-2xl border border-border bg-card/40 p-4">
					<h2 className="mb-2 font-semibold">Patient feedback (voice ratings)</h2>
					<ul className="space-y-1 text-sm">
						{data?.feedback.map((f) => (
							<li key={f.id} className="flex justify-between"><span>{f.booking_id}</span><span>{"★".repeat(f.rating)}{"☆".repeat(5 - f.rating)} {f.comment}</span></li>
						))}
						{data?.feedback.length === 0 ? <li className="text-muted-foreground">None yet.</li> : null}
					</ul>
				</div>
			</section>
		</main>
	);
}

function SessionCard({ s, pw, onChanged }: { s: Sess; pw: string; onChanged: () => void }) {
	const [text, setText] = useState("");
	const [note, setNote] = useState("");
	const code = s.lang.slice(0, 2);
	const speak = async (t: string) => {
		if (!t.trim()) return;
		try {
			await consoleFetch(`/session/${s.id}/speak`, pw, { method: "POST", body: JSON.stringify({ text: t, priority: "INTERRUPT" }) });
			setNote("Spoken through the agent");
			setText("");
			onChanged();
		} catch (e) {
			setNote((e as Error).message);
		}
	};
	const act = async (path: string) => {
		await consoleFetch(path, pw, { method: "POST" }).catch((e) => setNote((e as Error).message));
		onChanged();
	};
	const bytes = new TextEncoder().encode(text).length;
	return (
		<article className={`rounded-2xl border p-4 ${s.escalated ? "border-red-500 bg-red-500/10" : "border-border bg-card/40"}`}>
			<div className="flex items-center justify-between">
				<h2 className="font-semibold">{s.patient_name || s.patient_id} <span className="text-xs font-normal text-muted-foreground">{s.id}</span></h2>
				<div className="flex gap-1.5 text-[11px]">
					<span className="rounded bg-muted px-2 py-0.5">{s.stage}</span>
					<span className="rounded bg-muted px-2 py-0.5">{s.lang}</span>
					<span className={`rounded px-2 py-0.5 ${s.live ? "bg-emerald-500/20 text-emerald-300" : "bg-muted text-muted-foreground"}`}>{s.live ? "live" : "ended"}</span>
				</div>
			</div>
			{s.escalated ? (
				<p role="alert" className="mt-2 flex items-center gap-2 text-sm font-semibold text-red-200"><ShieldAlert className="h-4 w-4" aria-hidden /> Escalation: {s.escalation_reason.replace(/_/g, " ")}</p>
			) : null}
			<ul className="mt-3 space-y-1 text-sm">
				{s.transcript.map((l, i) => (
					<li key={`${l.role}-${i}`}><b className="text-muted-foreground">{l.role}:</b> {l.text}</li>
				))}
				{s.transcript.length === 0 ? <li className="text-muted-foreground">No transcript yet.</li> : null}
			</ul>
			{s.live ? (
				<div className="mt-3 space-y-2">
					<label className="text-xs font-medium text-muted-foreground" htmlFor={`sp-${s.id}`}>Speak as agent</label>
					<div className="flex gap-2">
						<input id={`sp-${s.id}`} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && speak(text)} className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm" placeholder="Type what the agent should say…" />
						<button type="button" onClick={() => speak(text)} className="rounded-lg bg-primary px-3 text-sm font-medium text-black">Speak</button>
					</div>
					<p className={`text-[11px] ${bytes > 512 ? "text-red-300" : "text-muted-foreground"}`}>{bytes}/512 bytes{bytes > 512 ? " (will be trimmed)" : ""}</p>
					<div className="flex flex-wrap gap-1.5">
						{(QUICK[code] ?? QUICK.en).map((q) => (
							<button key={q} type="button" onClick={() => speak(q)} className="rounded-full border border-border px-2.5 py-1 text-left text-xs hover:bg-muted">{q}</button>
						))}
					</div>
					<div className="flex gap-2 pt-1">
						{s.escalated ? <button type="button" onClick={() => act(`/console/${s.id}/resolve`)} className="rounded-lg border border-emerald-500/60 px-3 py-1.5 text-sm text-emerald-300">Resolve</button> : null}
						<button type="button" onClick={() => act(`/session/${s.id}/stop`)} className="rounded-lg border border-destructive px-3 py-1.5 text-sm text-red-300">End call</button>
					</div>
				</div>
			) : null}
			{note ? <p className="mt-2 text-xs text-muted-foreground" role="status">{note}</p> : null}
		</article>
	);
}
