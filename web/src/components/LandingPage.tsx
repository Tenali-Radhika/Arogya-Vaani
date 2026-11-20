"use client";

import type { RTMClient } from "agora-rtm";
import { Loader2 } from "lucide-react";
import dynamic from "next/dynamic";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElderToggle, LanguagePill } from "@/components/arogya/Controls";
import { DemoDrawer, IncomingCall, type IncomingCallInfo } from "@/components/arogya/Overlays";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { type AgentEvent, deriveState, useEvents } from "@/hooks/useEvents";
import {
	acceptCall,
	type GetConfigResponse,
	getConfig,
	type Lang,
	setElder,
	setLanguage,
	startAgent,
	stopAgent,
} from "@/services/api";
import type { AgoraRenewalTokens, AgoraTokenData, SessionInfo } from "@/types/conversation";

const ConversationComponent = dynamic(
	() => import("@/components/ConversationComponent"),
	{
		ssr: false,
	},
);

function waitForRtmConnected(rtmClient: RTMClient, timeoutMs = 600): Promise<void> {
	return new Promise((resolve) => {
		let settled = false;
		let timer: ReturnType<typeof setTimeout> | null = null;

		const finish = () => {
			if (settled) return;
			settled = true;
			if (timer) clearTimeout(timer);
			rtmClient.removeEventListener("status", onStatus);
			resolve();
		};

		const onStatus = (
			connectionStatus:
				| { newState?: string }
				| { state?: string }
				| Record<string, unknown>,
		) => {
			const nextState =
				typeof connectionStatus === "object" && connectionStatus !== null
					? "newState" in connectionStatus
						? connectionStatus.newState
						: "state" in connectionStatus
							? connectionStatus.state
							: undefined
					: undefined;
			if (nextState === "CONNECTED") {
				finish();
			}
		};

		rtmClient.addEventListener("status", onStatus);
		timer = setTimeout(finish, timeoutMs);
	});
}

const AgoraProvider = dynamic(
	async () => {
		const { AgoraRTCProvider, default: AgoraRTC } = await import(
			"agora-rtc-react"
		);

		return {
			default: function AgoraProviders({
				children,
			}: { children: React.ReactNode }) {
				const clientRef = useRef<ReturnType<
					typeof AgoraRTC.createClient
				> | null>(null);
				if (!clientRef.current) {
					clientRef.current = AgoraRTC.createClient({
						mode: "rtc",
						codec: "vp8",
					});
				}
				return (
					<AgoraRTCProvider client={clientRef.current}>
						{children}
					</AgoraRTCProvider>
				);
			},
		};
	},
	{ ssr: false },
);

export default function LandingPage() {
	const [showConversation, setShowConversation] = useState(false);
	const [agoraData, setAgoraData] = useState<AgoraTokenData | null>(null);
	const [rtmClient, setRtmClient] = useState<RTMClient | null>(null);
	const [session, setSession] = useState<SessionInfo | null>(null);
	const [isLoading, setIsLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [agentJoinError, setAgentJoinError] = useState(false);
	const [lang, setLang] = useState<Lang>("hi-IN");
	const [elder, setElderMode] = useState(false);
	const [demoMode, setDemoMode] = useState(false);
	const [patientId, setPatientId] = useState<string>("");
	const [incoming, setIncoming] = useState<IncomingCallInfo | null>(null);
	const busy = useRef(false);

	useEffect(() => {
		const q = new URLSearchParams(window.location.search);
		setDemoMode(q.get("demo") === "1");
		setPatientId(q.get("patient") ?? (q.get("demo") === "1" ? "lakshmi" : ""));
		import("agora-rtc-react").catch(() => {});
		import("agora-rtm").catch(() => {});
	}, []);

	useEffect(() => {
		document.documentElement.classList.toggle("elder", elder);
	}, [elder]);

	// Session events: tool timeline, doctors, appointment, red flag, language swaps.
	const onSessionEvent = useCallback((e: AgentEvent) => {
		if (e.type === "language_swap" && e.phase === "done") setLang(String(e.to) as Lang);
	}, []);
	const { events } = useEvents(session?.sessionId ?? null, onSessionEvent);
	const derived = useMemo(() => deriveState(events), [events]);

	// Proactive calls arrive on the patient channel, even when no call is active.
	const onPatientEvent = useCallback((e: AgentEvent) => {
		if (e.type === "incoming_call") setIncoming(e as unknown as IncomingCallInfo);
	}, []);
	useEvents(patientId ? `patient:${patientId}` : null, onPatientEvent);

	const connect = async (config: GetConfigResponse, begin: () => Promise<string | undefined>) => {
		const { default: AgoraRTM } = await import("agora-rtm");
		const [agentId, rtm] = await Promise.all([
			begin().catch((err) => {
				console.error("Failed to start conversation with agent:", err);
				setAgentJoinError(true);
				return undefined;
			}),
			(async () => {
				const nextRtm: RTMClient = new AgoraRTM.RTM(config.app_id, config.uid);
				await nextRtm.login({ token: config.token });
				await waitForRtmConnected(nextRtm);
				await nextRtm.subscribe(config.channel_name);
				return nextRtm;
			})(),
		]);
		setRtmClient(rtm);
		setSession({ sessionId: config.session_id, patientId: config.patient_id, patientName: config.patient_name });
		setAgoraData({
			token: config.token,
			uid: config.uid,
			channel: config.channel_name,
			appId: config.app_id,
			agentUid: config.agent_uid,
			agentId,
		});
		setShowConversation(true);
	};

	const handleStartConversation = async () => {
		if (busy.current) return;
		busy.current = true;
		setIsLoading(true);
		setError(null);
		setAgentJoinError(false);
		try {
			const config = await getConfig({ patient: patientId || undefined });
			const startLang = config.patient_name ? config.lang : lang;
			setLang(startLang);
			const useElder = elder || config.elder_mode;
			setElderMode(useElder);
			await connect(config, () =>
				startAgent(config.channel_name, Number(config.agent_uid), Number(config.uid), {
					sessionId: config.session_id,
					patientId: config.patient_id,
					lang: startLang,
					elderMode: useElder,
				}),
			);
		} catch (nextError) {
			setError("Could not start the call. Please try again.");
			console.error("Error starting conversation:", nextError);
		} finally {
			setIsLoading(false);
			busy.current = false;
		}
	};

	const handleAcceptCall = async () => {
		const call = incoming;
		if (!call || busy.current) return;
		busy.current = true;
		setIncoming(null);
		setIsLoading(true);
		setAgentJoinError(false);
		try {
			const config = await getConfig({ patient: String(call.patient_id) });
			setLang(call.lang as Lang);
			await connect(config, () =>
				acceptCall(call.followup_id, config.channel_name, Number(config.agent_uid), Number(config.uid), config.session_id),
			);
		} catch (nextError) {
			setError("Could not pick up the call.");
			console.error(nextError);
		} finally {
			setIsLoading(false);
			busy.current = false;
		}
	};

	const handleLanguageChange = useCallback(
		async (next: Lang) => {
			if (!session) return;
			try {
				await setLanguage(session.sessionId, next);
			} catch (err) {
				console.error("Language swap failed:", err);
			}
		},
		[session],
	);

	const handleElderChange = useCallback(
		async (on: boolean) => {
			setElderMode(on);
			if (session) await setElder(session.sessionId, on).catch(() => {});
		},
		[session],
	);

	const handleTokenWillExpire = useCallback(
		async (uid: string): Promise<AgoraRenewalTokens> => {
			if (!agoraData) throw new Error("Missing channel for token renewal");
			const [rtcConfig, rtmConfig] = await Promise.all([
				getConfig({ channel: agoraData.channel, uid }),
				getConfig({ channel: agoraData.channel, uid: agoraData.uid }),
			]);
			return { rtcToken: rtcConfig.token, rtmToken: rtmConfig.token };
		},
		[agoraData],
	);

	const handleEndConversation = async () => {
		if (session) {
			try {
				await stopAgent(session.sessionId);
			} catch (nextError) {
				console.error("Failed to stop agent:", nextError);
			}
		}
		rtmClient?.logout().catch((err) => console.error("RTM logout error:", err));
		setRtmClient(null);
		setAgoraData(null);
		setSession(null);
		setShowConversation(false);
	};

	return (
		<div className="relative flex h-dvh min-h-screen flex-col overflow-hidden bg-background text-foreground">
			<div className={`flex min-h-0 flex-1 flex-col ${showConversation ? "items-stretch" : "items-center justify-center"}`}>
				{!showConversation ? (
					<PreCall
						isLoading={isLoading}
						error={error}
						lang={lang}
						elder={elder}
						patientId={patientId}
						onLang={setLang}
						onElder={setElderMode}
						onStart={handleStartConversation}
					/>
				) : agoraData && rtmClient && session ? (
					<>
						{agentJoinError ? (
							<div className="mx-4 mt-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive" role="alert">
								Could not connect the voice agent. Check the backend and CUSTOM_LLM_URL.
							</div>
						) : null}
						<Suspense fallback={<LoadingSkeleton />}>
							<ErrorBoundary>
								<AgoraProvider>
									<ConversationComponent
										agoraData={agoraData}
										rtmClient={rtmClient}
										session={session}
										lang={lang}
										elder={elder}
										events={events}
										derived={derived}
										onLanguageChange={handleLanguageChange}
										onElderChange={handleElderChange}
										onTokenWillExpire={handleTokenWillExpire}
										onEndConversation={handleEndConversation}
									/>
								</AgoraProvider>
							</ErrorBoundary>
						</Suspense>
					</>
				) : (
					<p className="text-sm text-muted-foreground">Failed to load conversation data.</p>
				)}
			</div>
			{incoming && !showConversation ? (
				<IncomingCall call={incoming} onAccept={handleAcceptCall} onDecline={() => setIncoming(null)} />
			) : null}
			{demoMode ? <DemoDrawer /> : null}
			<footer className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex justify-end px-4 py-3 text-xs text-muted-foreground">
				Demo uses fictional doctors. Guidance only, never a diagnosis. In an emergency call 108.
			</footer>
		</div>
	);
}

function PreCall({
	isLoading,
	error,
	lang,
	elder,
	patientId,
	onLang,
	onElder,
	onStart,
}: {
	isLoading: boolean;
	error: string | null;
	lang: Lang;
	elder: boolean;
	patientId: string;
	onLang: (l: Lang) => void;
	onElder: (v: boolean) => void;
	onStart: () => void;
}) {
	return (
		<div className="mx-auto flex w-[min(94vw,28rem)] animate-fade-up flex-col items-center gap-6 rounded-3xl border border-border bg-card/70 px-8 py-10 text-center shadow-2xl">
			<div>
				<h1 className="text-3xl font-semibold tracking-tight">ArogyaVaani</h1>
				<p className="mt-1 text-lg text-primary">आरोग्य वाणी · ಆರೋಗ್ಯ ವಾಣಿ</p>
				<p className="mt-3 text-sm leading-6 text-muted-foreground">
					Talk to a doctor-booking assistant in Hindi, Kannada or English. No app to learn, no forms. It finds a doctor
					who speaks your language, books the slot, and calls you back with a reminder.
				</p>
			</div>
			<button
				type="button"
				onClick={onStart}
				disabled={isLoading}
				aria-label="Start talking to ArogyaVaani"
				className="flex h-40 w-40 items-center justify-center rounded-full bg-primary px-4 text-lg font-bold leading-snug text-black shadow-[0_0_0_12px_hsl(var(--primary)/0.18)] transition-transform hover:scale-105 focus-visible:outline focus-visible:outline-4 focus-visible:outline-offset-4 focus-visible:outline-white disabled:opacity-70"
			>
				{isLoading ? <Loader2 className="h-12 w-12 animate-spin" aria-hidden /> : "बोलिए · ಮಾತನಾಡಿ · Talk"}
			</button>
			<LanguagePill lang={lang} onChange={onLang} />
			<ElderToggle on={elder} onChange={onElder} />
			{patientId ? <p className="text-xs text-muted-foreground">Demo patient: {patientId}</p> : null}
			{error ? (
				<p className="text-sm text-destructive" role="alert">
					{error}
				</p>
			) : null}
		</div>
	);
}
