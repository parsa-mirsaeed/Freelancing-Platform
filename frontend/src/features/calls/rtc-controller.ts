import { getIceServers, type CallSession, type CallType } from "@/lib/api/calls";
import type { RealtimeSocketClient } from "@/lib/realtime/socket-client";

export type CallPhase =
  | "idle"
  | "preparing"
  | "ringing"
  | "incoming"
  | "connecting"
  | "active"
  | "reconnect-required"
  | "ended";

export interface CallControllerCallbacks {
  onCall: (call: CallSession | null) => void;
  onPhase: (phase: CallPhase) => void;
  onLocalStream: (stream: MediaStream | null) => void;
  onRemoteStream: (stream: MediaStream | null) => void;
  onMediaState: (state: { muted: boolean; cameraOff: boolean; screenSharing: boolean }) => void;
  onError: (message: string) => void;
}

type SocketAck = {
  ok: boolean;
  call?: CallSession;
  error?: { detail?: string };
};

type DescriptionEvent = {
  call_id: string;
  description: RTCSessionDescriptionInit;
};

type CandidateEvent = {
  call_id: string;
  candidate: RTCIceCandidateInit;
};

type CallEvent = { call: CallSession };

function isCallEvent(payload: unknown): payload is CallEvent {
  if (!payload || typeof payload !== "object") return false;
  const call = (payload as { call?: unknown }).call;
  return Boolean(call && typeof call === "object" && typeof (call as { id?: unknown }).id === "string");
}

function isDescriptionEvent(payload: unknown): payload is DescriptionEvent {
  if (!payload || typeof payload !== "object") return false;
  const value = payload as { call_id?: unknown; description?: unknown };
  return typeof value.call_id === "string" && Boolean(value.description && typeof value.description === "object");
}

function isCandidateEvent(payload: unknown): payload is CandidateEvent {
  if (!payload || typeof payload !== "object") return false;
  const value = payload as { call_id?: unknown; candidate?: unknown };
  return typeof value.call_id === "string" && Boolean(value.candidate && typeof value.candidate === "object");
}

export function mediaConstraints(callType: CallType): MediaStreamConstraints {
  return { audio: true, video: callType === "VIDEO" };
}

export class WebRtcCallController {
  private currentCall: CallSession | null = null;
  private peer: RTCPeerConnection | null = null;
  private localStream: MediaStream | null = null;
  private remoteStream: MediaStream | null = null;
  private screenStream: MediaStream | null = null;
  private pendingCandidates: RTCIceCandidateInit[] = [];
  private muted = false;
  private cameraOff = false;
  private screenSharing = false;
  private disposed = false;

  constructor(
    private readonly client: RealtimeSocketClient,
    private readonly userId: string,
    private readonly callbacks: CallControllerCallbacks,
  ) {}

  restore(call: CallSession | null): void {
    this.currentCall = call;
    this.callbacks.onCall(call);
    if (!call) {
      this.callbacks.onPhase("idle");
      return;
    }
    if (call.status === "INVITED") {
      this.callbacks.onPhase(call.caller_user_id === this.userId ? "ringing" : "incoming");
      return;
    }
    if (call.status === "ACTIVE") {
      this.callbacks.onPhase("reconnect-required");
      return;
    }
    this.callbacks.onPhase("ended");
  }

  async start(conversationId: string, callType: CallType): Promise<void> {
    if (this.currentCall && this.currentCall.status !== "ENDED") {
      throw new Error("End the current call before starting another one.");
    }
    this.callbacks.onPhase("preparing");
    try {
      await this.ensureLocalMedia(callType);
      const ack = await this.client.emit<SocketAck>("call.invite", {
        conversation_id: conversationId,
        client_call_id: crypto.randomUUID(),
        call_type: callType,
      });
      const call = this.requireCallAck(ack, "Call invitation was rejected.");
      this.currentCall = call;
      this.callbacks.onCall(call);
      this.callbacks.onPhase("ringing");
    } catch (error) {
      this.cleanupPeerAndMedia();
      this.callbacks.onPhase("idle");
      throw error;
    }
  }

  async accept(): Promise<void> {
    const call = this.currentCall;
    if (!call || call.status !== "INVITED" || call.callee_user_id !== this.userId) {
      throw new Error("There is no incoming call to accept.");
    }
    this.callbacks.onPhase("preparing");
    await this.ensureLocalMedia(call.call_type);
    const ack = await this.client.emit<SocketAck>("call.accept", { call_id: call.id });
    const active = this.requireCallAck(ack, "Call acceptance was rejected.");
    this.currentCall = active;
    this.callbacks.onCall(active);
    this.callbacks.onPhase("connecting");
  }

  async end(reason = "ended_by_user"): Promise<void> {
    const call = this.currentCall;
    if (call && call.status !== "ENDED" && this.client.isLive()) {
      try {
        const ack = await this.client.emit<SocketAck>("call.end", { call_id: call.id, reason });
        if (ack.ok && ack.call) {
          this.currentCall = ack.call;
          this.callbacks.onCall(ack.call);
        }
      } catch {
        // Local media must still stop even if the signaling transport disappears.
      }
    }
    this.cleanupPeerAndMedia();
    this.callbacks.onPhase("ended");
  }

  async decline(): Promise<void> {
    await this.end("declined");
  }

  toggleMute(): void {
    this.muted = !this.muted;
    for (const track of this.localStream?.getAudioTracks() ?? []) track.enabled = !this.muted;
    this.publishMediaState();
  }

  toggleCamera(): void {
    if (!this.currentCall || this.currentCall.call_type !== "VIDEO" || this.screenSharing) return;
    this.cameraOff = !this.cameraOff;
    for (const track of this.localStream?.getVideoTracks() ?? []) track.enabled = !this.cameraOff;
    this.publishMediaState();
  }

  async startScreenShare(): Promise<void> {
    if (!this.currentCall || this.currentCall.call_type !== "VIDEO" || !this.peer) {
      throw new Error("Screen sharing is available during an active video call.");
    }
    if (!navigator.mediaDevices?.getDisplayMedia) {
      throw new Error("Screen sharing is not supported by this browser.");
    }
    const sender = this.peer.getSenders().find((item) => item.track?.kind === "video");
    if (!sender) throw new Error("The video sender is not available.");

    const screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    const screenTrack = screenStream.getVideoTracks()[0];
    if (!screenTrack) {
      for (const track of screenStream.getTracks()) track.stop();
      throw new Error("Screen capture did not return a video track.");
    }
    await sender.replaceTrack(screenTrack);
    this.screenStream = screenStream;
    this.screenSharing = true;
    this.callbacks.onLocalStream(screenStream);
    this.publishMediaState();
    screenTrack.addEventListener("ended", () => void this.stopScreenShare());
  }

  async stopScreenShare(): Promise<void> {
    if (!this.screenSharing) return;
    const sender = this.peer?.getSenders().find((item) => item.track?.kind === "video") ?? null;
    const cameraTrack = this.localStream?.getVideoTracks()[0] ?? null;
    if (sender) await sender.replaceTrack(cameraTrack);
    for (const track of this.screenStream?.getTracks() ?? []) track.stop();
    this.screenStream = null;
    this.screenSharing = false;
    this.callbacks.onLocalStream(this.localStream);
    this.publishMediaState();
  }

  async handleEvent(event: string, payload: unknown): Promise<void> {
    if (this.disposed) return;
    if (event === "call.invite" && isCallEvent(payload)) {
      if (this.currentCall && this.currentCall.status !== "ENDED") {
        if (payload.call.id !== this.currentCall.id && this.client.isLive()) {
          void this.client.emit("call.end", { call_id: payload.call.id, reason: "busy" }).catch(() => undefined);
        }
        return;
      }
      this.currentCall = payload.call;
      this.callbacks.onCall(payload.call);
      this.callbacks.onPhase("incoming");
      return;
    }
    if (event === "call.accept" && isCallEvent(payload)) {
      if (payload.call.id !== this.currentCall?.id) return;
      this.currentCall = payload.call;
      this.callbacks.onCall(payload.call);
      this.callbacks.onPhase("connecting");
      await this.createAndSendOffer(payload.call);
      return;
    }
    if (event === "webrtc.offer" && isDescriptionEvent(payload)) {
      if (payload.call_id !== this.currentCall?.id) return;
      await this.acceptOffer(payload.description);
      return;
    }
    if (event === "webrtc.answer" && isDescriptionEvent(payload)) {
      if (payload.call_id !== this.currentCall?.id || !this.peer) return;
      await this.peer.setRemoteDescription(payload.description);
      await this.flushCandidates();
      this.callbacks.onPhase("active");
      return;
    }
    if (event === "webrtc.ice_candidate" && isCandidateEvent(payload)) {
      if (payload.call_id !== this.currentCall?.id) return;
      if (!this.peer || !this.peer.remoteDescription) {
        this.pendingCandidates.push(payload.candidate);
      } else {
        await this.peer.addIceCandidate(payload.candidate);
      }
      return;
    }
    if (event === "call.end" && isCallEvent(payload)) {
      if (payload.call.id !== this.currentCall?.id) return;
      this.currentCall = payload.call;
      this.callbacks.onCall(payload.call);
      this.cleanupPeerAndMedia();
      this.callbacks.onPhase("ended");
    }
  }

  dispose(): void {
    this.disposed = true;
    this.cleanupPeerAndMedia();
  }

  private async createAndSendOffer(call: CallSession): Promise<void> {
    await this.ensureLocalMedia(call.call_type);
    const peer = await this.ensurePeer();
    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    const ack = await this.client.emit<SocketAck>("webrtc.offer", {
      call_id: call.id,
      description: peer.localDescription ?? offer,
    });
    if (!ack.ok) throw new Error(ack.error?.detail || "WebRTC offer was rejected.");
  }

  private async acceptOffer(description: RTCSessionDescriptionInit): Promise<void> {
    const call = this.currentCall;
    if (!call || call.status !== "ACTIVE") throw new Error("The call is not active.");
    await this.ensureLocalMedia(call.call_type);
    const peer = await this.ensurePeer();
    await peer.setRemoteDescription(description);
    await this.flushCandidates();
    const answer = await peer.createAnswer();
    await peer.setLocalDescription(answer);
    const ack = await this.client.emit<SocketAck>("webrtc.answer", {
      call_id: call.id,
      description: peer.localDescription ?? answer,
    });
    if (!ack.ok) throw new Error(ack.error?.detail || "WebRTC answer was rejected.");
    this.callbacks.onPhase("active");
  }

  private async ensureLocalMedia(callType: CallType): Promise<MediaStream> {
    if (this.localStream) return this.localStream;
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Camera/microphone access is not supported by this browser.");
    }
    const stream = await navigator.mediaDevices.getUserMedia(mediaConstraints(callType));
    this.localStream = stream;
    this.callbacks.onLocalStream(stream);
    return stream;
  }

  private async ensurePeer(): Promise<RTCPeerConnection> {
    if (this.peer) return this.peer;
    const localStream = this.localStream;
    if (!localStream) throw new Error("Local media must be ready before peer negotiation.");
    const config = await getIceServers();
    const peer = new RTCPeerConnection({ iceServers: config.ice_servers });
    for (const track of localStream.getTracks()) peer.addTrack(track, localStream);
    peer.addEventListener("icecandidate", (event) => {
      if (!event.candidate || !this.currentCall || !this.client.isLive()) return;
      void this.client
        .emit<SocketAck>("webrtc.ice_candidate", {
          call_id: this.currentCall.id,
          candidate: event.candidate.toJSON(),
        })
        .catch((error: unknown) => this.reportError(error));
    });
    peer.addEventListener("track", (event) => {
      const stream = event.streams[0] ?? this.remoteStream ?? new MediaStream();
      if (!event.streams[0] && !stream.getTracks().some((track) => track.id === event.track.id)) {
        stream.addTrack(event.track);
      }
      this.remoteStream = stream;
      this.callbacks.onRemoteStream(stream);
    });
    peer.addEventListener("connectionstatechange", () => {
      if (peer.connectionState === "connected") this.callbacks.onPhase("active");
      if (peer.connectionState === "failed") this.callbacks.onError("The peer-to-peer connection failed.");
      if (peer.connectionState === "closed") this.callbacks.onPhase("ended");
    });
    this.peer = peer;
    return peer;
  }

  private async flushCandidates(): Promise<void> {
    if (!this.peer?.remoteDescription) return;
    const pending = this.pendingCandidates.splice(0);
    for (const candidate of pending) await this.peer.addIceCandidate(candidate);
  }

  private requireCallAck(ack: SocketAck, fallback: string): CallSession {
    if (!ack.ok || !ack.call) throw new Error(ack.error?.detail || fallback);
    return ack.call;
  }

  private cleanupPeerAndMedia(): void {
    this.peer?.close();
    this.peer = null;
    for (const track of this.screenStream?.getTracks() ?? []) track.stop();
    for (const track of this.localStream?.getTracks() ?? []) track.stop();
    for (const track of this.remoteStream?.getTracks() ?? []) track.stop();
    this.screenStream = null;
    this.localStream = null;
    this.remoteStream = null;
    this.pendingCandidates = [];
    this.screenSharing = false;
    this.muted = false;
    this.cameraOff = false;
    this.callbacks.onLocalStream(null);
    this.callbacks.onRemoteStream(null);
    this.publishMediaState();
  }

  private publishMediaState(): void {
    this.callbacks.onMediaState({
      muted: this.muted,
      cameraOff: this.cameraOff,
      screenSharing: this.screenSharing,
    });
  }

  private reportError(error: unknown): void {
    this.callbacks.onError(error instanceof Error ? error.message : "WebRTC signaling failed.");
  }
}
