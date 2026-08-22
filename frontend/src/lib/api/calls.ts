import { productJson } from "@/lib/api/product-client";

export type CallType = "VOICE" | "VIDEO";
export type CallStatus = "INVITED" | "ACTIVE" | "ENDED";

export interface CallSession {
  id: string;
  conversation_id: string;
  caller_user_id: string;
  callee_user_id: string;
  client_call_id: string;
  call_type: CallType;
  status: CallStatus;
  created_at: string;
  accepted_at: string | null;
  ended_at: string | null;
  ended_by_user_id: string | null;
  end_reason: string | null;
}

export interface IceServerConfiguration {
  ice_servers: RTCIceServer[];
  expires_at: string;
  ttl_seconds: number;
}

export function getIceServers(): Promise<IceServerConfiguration> {
  return productJson<IceServerConfiguration>("calls/ice-servers");
}

export function getCall(callId: string): Promise<CallSession> {
  return productJson<CallSession>(`calls/${callId}`);
}

export async function getLiveConversationCall(conversationId: string): Promise<CallSession | null> {
  const payload = await productJson<{ call: CallSession | null }>(
    `conversations/${conversationId}/call`,
  );
  return payload.call;
}
