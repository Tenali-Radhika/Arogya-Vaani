import type { RTMClient } from 'agora-rtm';
import type { AgentEvent, DerivedState } from '@/hooks/useEvents';
import type { Lang } from '@/services/api';

/** Session bootstrap from GET /api/get_config (channel + tokens + agent identity). */
export interface AgoraTokenData {
  token: string;
  uid: string;
  channel: string;
  agentId?: string;
  appId?: string; // `app_id` returned by backend
  agentUid?: string; // agent RTC uid returned by the backend
}

export interface AgoraRenewalTokens {
  rtcToken: string;
  rtmToken: string;
}

export interface SessionInfo {
  sessionId: string;
  patientId: string;
  patientName: string;
}

export interface ConversationComponentProps {
  agoraData: AgoraTokenData;
  rtmClient: RTMClient;
  session: SessionInfo;
  lang: Lang;
  elder: boolean;
  events: AgentEvent[];
  derived: DerivedState;
  onLanguageChange: (lang: Lang) => void;
  onElderChange: (on: boolean) => void;
  onTokenWillExpire: (uid: string) => Promise<AgoraRenewalTokens>;
  onEndConversation: () => void;
}
