"use client";

import { Activity, ListTree } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

type Props = {
	statusPanel: ReactNode;
	pipelineMetrics: ReactNode;
	transcriptPanel: ReactNode;
	patientPane: ReactNode;
	timelinePanel: ReactNode;
	toolbar: ReactNode;
	p50Ms: number | null;
	onEndConversation: () => void;
};

export function ArogyaLayout({
	statusPanel,
	pipelineMetrics,
	transcriptPanel,
	patientPane,
	timelinePanel,
	toolbar,
	p50Ms,
	onEndConversation,
}: Props) {
	const [showTimeline, setShowTimeline] = useState(true);
	return (
		<div className="flex min-h-0 flex-1 flex-col text-left">
			<header className="flex shrink-0 flex-col gap-3 border-b border-border px-4 py-3 md:flex-row md:items-center md:justify-between md:px-6">
				<div className="flex min-w-0 flex-col gap-1">
					<h1 className="truncate text-lg font-semibold leading-none tracking-[-0.02em]">
						ArogyaVaani <span className="font-normal text-muted-foreground">· health in your language</span>
					</h1>
					<p className="text-xs text-muted-foreground">Powered by Agora ConvoAI · Murf Falcon · AWS</p>
					<div className="mt-1">{pipelineMetrics}</div>
				</div>
				<div className="flex flex-wrap items-center gap-2">
					{p50Ms ? (
						<span title="Median turn latency (our endpoint: LLM + tools)" className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs tabular-nums text-muted-foreground">
							<Activity className="h-3.5 w-3.5" aria-hidden /> p50 {p50Ms} ms
						</span>
					) : null}
					{toolbar}
					<button
						type="button"
						onClick={() => setShowTimeline((s) => !s)}
						aria-pressed={showTimeline}
						className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted"
					>
						<ListTree className="h-4 w-4" aria-hidden /> Agent actions
					</button>
					{statusPanel}
					<Button
						variant="destructive"
						size="sm"
						className="h-8 rounded-md border border-destructive bg-transparent px-3 text-xs font-medium text-destructive hover:bg-destructive/10"
						onClick={onEndConversation}
						aria-label="End the call"
					>
						End call
					</Button>
				</div>
			</header>

			<div className="flex min-h-0 w-full flex-1 flex-col gap-4 overflow-y-auto px-4 pb-20 pt-4 md:px-6 lg:flex-row lg:overflow-hidden lg:pb-4">
				<aside className="order-2 h-72 min-h-0 w-full shrink-0 lg:order-1 lg:h-full lg:w-[22rem]">{transcriptPanel}</aside>
				<main className="order-1 flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto lg:order-2 lg:border-l lg:border-border/80 lg:pl-6">
					{patientPane}
				</main>
				{showTimeline ? (
					<aside className="order-3 h-80 min-h-0 w-full shrink-0 lg:h-full lg:w-[24rem]">{timelinePanel}</aside>
				) : null}
			</div>
		</div>
	);
}
