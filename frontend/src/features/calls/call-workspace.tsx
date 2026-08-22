"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { getLiveConversationCall, type CallSession, type CallType } from "@/lib/api/calls";
import { listConversations, type Conversation } from "@/lib/api/communication";
import {
  configuredRealtimeUrl,
  RealtimeSocketClient,
  type RealtimeState,
} from "@/lib/realtime/socket-client";

import styles from "./calls.module.css";
import {
  WebRtcCallController,
  type CallPhase,
} from "./rtc-controller";

function conversationLabel(conversation: Conversation, userId: string): string {
  const peer = conversation.members.find((member) => member.user_id !== userId);
  return peer ? `Conversation with ${peer.user_id.slice(0, 8)}…` : "Contract conversation";
}

function phaseLabel(phase: CallPhase): string {
  if (phase === "preparing") return "Preparing media";
  if (phase === "ringing") return "Ringing";
  if (phase === "incoming") return "Incoming call";
  if (phase === "connecting") return "Negotiating peer connection";
  if (phase === "active") return "Connected";
  if (phase === "reconnect-required") return "Call state recovered";
  if (phase === "ended") return "Ended";
  return "Ready";
}

function invitedConversationId(event: string, payload: unknown): string | null {
  if (event !== "call.invite" || !payload || typeof payload !== "object") return null;
  const call = (payload as { call?: unknown }).call;
  if (!call || typeof call !== "object") return null;
  const conversationId = (call as { conversation_id?: unknown }).conversation_id;
  return typeof conversationId === "string" ? conversationId : null;
}

export function CallWorkspace() {
  const { user, status } = useSession();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [transport, setTransport] = useState<RealtimeState>(
    configuredRealtimeUrl() ? "connecting" : "fallback",
  );
  const [peerOnline, setPeerOnline] = useState<boolean | null>(null);
  const [callType, setCallType] = useState<CallType>("VIDEO");
  const [call, setCall] = useState<CallSession | null>(null);
  const [phase, setPhase] = useState<CallPhase>("idle");
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const [muted, setMuted] = useState(false);
  const [cameraOff, setCameraOff] = useState(false);
  const [screenSharing, setScreenSharing] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const callRef = useRef<CallSession | null>(null);
  const controllerRef = useRef<WebRtcCallController | null>(null);
  const localVideoRef = useRef<HTMLVideoElement | null>(null);
  const remoteVideoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    if (localVideoRef.current) localVideoRef.current.srcObject = localStream;
  }, [localStream]);

  useEffect(() => {
    if (remoteVideoRef.current) remoteVideoRef.current.srcObject = remoteStream;
  }, [remoteStream]);

  useEffect(() => {
    if (status !== "authenticated" || !user) return;
    const controller = new AbortController();
    void listConversations(controller.signal)
      .then((items) => {
        if (controller.signal.aborted) return;
        setConversations(items);
        setSelectedId((current) => current || items[0]?.id || "");
        setError("");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load call conversations.");
      });
    return () => controller.abort();
  }, [status, user]);

  useEffect(() => {
    if (!selectedId || !user) return;
    let cancelled = false;
    const baseUrl = configuredRealtimeUrl();

    if (!baseUrl) {
      void getLiveConversationCall(selectedId)
        .then((liveCall) => {
          if (cancelled) return;
          callRef.current = liveCall;
          setCall(liveCall);
          if (!liveCall) setPhase("idle");
          else if (liveCall.status === "INVITED") {
            setPhase(liveCall.caller_user_id === user.id ? "ringing" : "incoming");
          } else if (liveCall.status === "ACTIVE") setPhase("reconnect-required");
          else setPhase("ended");
        })
        .catch((reason: unknown) => {
          if (!cancelled) {
            setError(reason instanceof Error ? reason.message : "Unable to recover call state.");
          }
        });
      return () => {
        cancelled = true;
      };
    }

    let recovered = false;
    const controllerCallbacks = {
      onCall: (nextCall: CallSession | null) => {
        callRef.current = nextCall;
        setCall(nextCall);
      },
      onPhase: setPhase,
      onLocalStream: setLocalStream,
      onRemoteStream: setRemoteStream,
      onMediaState: (media: { muted: boolean; cameraOff: boolean; screenSharing: boolean }) => {
        setMuted(media.muted);
        setCameraOff(media.cameraOff);
        setScreenSharing(media.screenSharing);
      },
      onError: setError,
    };
    const client = new RealtimeSocketClient(baseUrl, selectedId, {
      onState: (next) => {
        if (cancelled) return;
        setTransport(next);
        if (next !== "live") return;

        const activeController = controllerRef.current;
        if (!activeController || recovered) {
          void client
            .emit<{
              ok: boolean;
              members?: Array<{ user_id: string; online: boolean }>;
            }>("presence.query", { conversation_id: selectedId })
            .then((presence) => {
              if (cancelled || !presence.ok || !presence.members) return;
              const peer = presence.members.find((member) => member.user_id !== user.id);
              setPeerOnline(peer?.online ?? null);
            })
            .catch(() => undefined);
          return;
        }

        recovered = true;
        void Promise.all([
          getLiveConversationCall(selectedId),
          client.emit<{
            ok: boolean;
            members?: Array<{ user_id: string; online: boolean }>;
          }>("presence.query", { conversation_id: selectedId }),
        ])
          .then(([liveCall, presence]) => {
            if (cancelled || controllerRef.current !== activeController) return;
            activeController.restore(liveCall);
            if (presence.ok && presence.members) {
              const peer = presence.members.find((member) => member.user_id !== user.id);
              setPeerOnline(peer?.online ?? null);
            }
          })
          .catch((reason: unknown) => {
            if (!cancelled) {
              setError(reason instanceof Error ? reason.message : "Unable to recover call state.");
            }
          });
      },
      onEvent: (event, payload) => {
        const activeController = controllerRef.current;
        const incomingConversation = invitedConversationId(event, payload);
        if (incomingConversation && incomingConversation !== selectedId) {
          if (callRef.current && callRef.current.status !== "ENDED") {
            if (activeController) {
              void activeController.handleEvent(event, payload).catch((reason: unknown) => {
                setError(reason instanceof Error ? reason.message : "Unable to reject a competing call.");
              });
            }
            return;
          }
          callRef.current = null;
          setCall(null);
          setPhase("idle");
          setLocalStream(null);
          setRemoteStream(null);
          setPeerOnline(null);
          setMessage("");
          setError("");
          setSelectedId(incomingConversation);
          return;
        }
        if (!activeController) return;
        void activeController.handleEvent(event, payload).catch((reason: unknown) => {
          setError(reason instanceof Error ? reason.message : "WebRTC signaling failed.");
        });
      },
    });
    const callController = new WebRtcCallController(client, user.id, controllerCallbacks);
    controllerRef.current = callController;
    client.start();

    return () => {
      cancelled = true;
      callController.dispose();
      if (controllerRef.current === callController) controllerRef.current = null;
      client.stop();
    };
  }, [selectedId, user]);

  const selectedConversation = useMemo(
    () => conversations.find((item) => item.id === selectedId) ?? null,
    [conversations, selectedId],
  );

  function selectConversation(conversationId: string) {
    if (conversationId === selectedId) return;
    if (callRef.current && callRef.current.status !== "ENDED") {
      setError("End the current call before switching conversations.");
      return;
    }
    callRef.current = null;
    setCall(null);
    setPhase("idle");
    setLocalStream(null);
    setRemoteStream(null);
    setPeerOnline(null);
    setMessage("");
    setError("");
    setSelectedId(conversationId);
  }

  async function run(action: string, task: () => Promise<void>, success?: string) {
    setBusy(action);
    setError("");
    setMessage("");
    try {
      await task();
      if (success) setMessage(success);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Call action failed.");
    } finally {
      setBusy("");
    }
  }

  function start(type: CallType) {
    const controller = controllerRef.current;
    if (!controller || !selectedId) return;
    setCallType(type);
    void run(`start:${type}`, () => controller.start(selectedId, type));
  }

  if (status === "loading") {
    return <main className={styles.page}><p className={styles.empty}>Opening calls workspace…</p></main>;
  }
  if (!user) return null;

  const liveTransport = transport === "live";
  const hasLiveCall = Boolean(call && call.status !== "ENDED");
  const incoming = phase === "incoming" && call?.callee_user_id === user.id;
  const videoCall = call?.call_type === "VIDEO" || (!hasLiveCall && callType === "VIDEO");
  const controlsVisible = ["connecting", "active"].includes(phase);

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>WebRTC · one-to-one</span>
          <h1>Voice and video stay peer to peer.</h1>
          <p>
            Socket.IO carries only authenticated signaling. Media flows directly between browsers through WebRTC, with short-lived session-bound STUN/TURN credentials from the backend.
          </p>
        </div>
        <aside>
          <strong>{phaseLabel(phase)}</strong>
          <p>{liveTransport ? "Realtime signaling is connected." : "Realtime signaling is unavailable; calls cannot be changed until it reconnects."}</p>
        </aside>
      </section>

      {error ? <p className={styles.errorBanner} role="alert">{error}</p> : null}
      {message ? <p className={styles.banner} role="status">{message}</p> : null}

      <section className={styles.workspace} aria-label="WebRTC calls workspace">
        <aside className={styles.sidebar}>
          <span className={styles.eyebrow}>Private threads</span>
          <h2>Choose a conversation</h2>
          {conversations.length ? (
            <ul className={styles.conversationList}>
              {conversations.map((conversation) => (
                <li key={conversation.id}>
                  <button
                    type="button"
                    aria-current={conversation.id === selectedId}
                    onClick={() => selectConversation(conversation.id)}
                  >
                    <strong>{conversationLabel(conversation, user.id)}</strong>
                    <span>{conversation.contract_id ? `Contract ${conversation.contract_id.slice(0, 8)}…` : "Private conversation"}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className={styles.empty}>No private contract conversations are available yet.</p>}
        </aside>

        <div className={styles.callStage}>
          <header className={styles.callHeader}>
            <div>
              <span className={styles.eyebrow}>Current call</span>
              <h2>{selectedConversation ? conversationLabel(selectedConversation, user.id) : "Select a conversation"}</h2>
              <p>
                {peerOnline === null ? "Presence unknown" : peerOnline ? "Other party online" : "Other party offline — an invitation can still be recovered later."}
              </p>
            </div>
            <span className={styles.transport} data-state={transport}>{transport === "live" ? "Live signaling" : transport === "connecting" ? "Connecting" : "Signaling offline"}</span>
          </header>

          <div className={styles.videoGrid} data-video={videoCall}>
            <div className={styles.remoteFrame}>
              <video ref={remoteVideoRef} autoPlay playsInline />
              <span>{remoteStream ? "Remote media" : phase === "active" ? "Waiting for remote media…" : phaseLabel(phase)}</span>
            </div>
            <div className={styles.localFrame}>
              <video ref={localVideoRef} autoPlay playsInline muted />
              <span>{screenSharing ? "Your screen" : localStream ? "You" : "Local preview"}</span>
            </div>
          </div>

          <div className={styles.callActions}>
            {!hasLiveCall ? (
              <>
                <button type="button" disabled={!selectedId || !liveTransport || Boolean(busy)} onClick={() => start("VOICE")}>{busy === "start:VOICE" ? "Preparing…" : "Start voice call"}</button>
                <button className={styles.primary} type="button" disabled={!selectedId || !liveTransport || Boolean(busy)} onClick={() => start("VIDEO")}>{busy === "start:VIDEO" ? "Preparing…" : "Start video call"}</button>
              </>
            ) : null}

            {incoming ? (
              <>
                <button className={styles.primary} type="button" disabled={!liveTransport || Boolean(busy)} onClick={() => {
                  const controller = controllerRef.current;
                  if (controller) void run("accept", () => controller.accept());
                }}>{busy === "accept" ? "Opening media…" : `Accept ${call?.call_type.toLowerCase()} call`}</button>
                <button type="button" disabled={!liveTransport || Boolean(busy)} onClick={() => {
                  const controller = controllerRef.current;
                  if (controller) void run("decline", () => controller.decline(), "Call declined.");
                }}>Decline</button>
              </>
            ) : null}

            {controlsVisible ? (
              <>
                <button type="button" disabled={Boolean(busy)} onClick={() => controllerRef.current?.toggleMute()}>{muted ? "Unmute" : "Mute"}</button>
                {call?.call_type === "VIDEO" ? <button type="button" disabled={Boolean(busy) || screenSharing} onClick={() => controllerRef.current?.toggleCamera()}>{cameraOff ? "Camera on" : "Camera off"}</button> : null}
                {call?.call_type === "VIDEO" ? (
                  <button type="button" disabled={phase !== "active" || Boolean(busy)} onClick={() => {
                    const controller = controllerRef.current;
                    if (!controller) return;
                    void run("screen", () => screenSharing ? controller.stopScreenShare() : controller.startScreenShare());
                  }}>{busy === "screen" ? "Switching…" : screenSharing ? "Stop sharing" : "Share screen"}</button>
                ) : null}
              </>
            ) : null}

            {hasLiveCall ? <button className={styles.danger} type="button" disabled={!liveTransport || Boolean(busy)} onClick={() => {
              const controller = controllerRef.current;
              if (controller) void run("end", () => controller.end(), "Call ended.");
            }}>{busy === "end" ? "Ending…" : phase === "reconnect-required" ? "End recovered call" : "End call"}</button> : null}
          </div>

          {phase === "reconnect-required" ? (
            <p className={styles.notice}>
              The backend recovered an active call after this page reloaded. SDP and ICE are intentionally ephemeral, so this browser cannot silently recreate the old media path. End the recovered call and start a new one.
            </p>
          ) : null}
        </div>
      </section>
    </main>
  );
}
