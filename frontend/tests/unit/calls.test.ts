import { beforeEach, describe, expect, it, vi } from "vitest";

import { getIceServers, getLiveConversationCall, type CallSession } from "@/lib/api/calls";
import { WebRtcCallController, mediaConstraints } from "@/features/calls/rtc-controller";

vi.mock("@/lib/api/product-client", () => ({
  productJson: vi.fn(),
}));

import { productJson } from "@/lib/api/product-client";

const activeVideoCall: CallSession = {
  id: "call-1",
  conversation_id: "conversation-1",
  caller_user_id: "user-1",
  callee_user_id: "user-2",
  client_call_id: "client-call-1",
  call_type: "VIDEO",
  status: "ACTIVE",
  created_at: "2026-08-22T18:00:00Z",
  accepted_at: "2026-08-22T18:00:05Z",
  ended_at: null,
  ended_by_user_id: null,
  end_reason: null,
};

describe("calls API and browser media contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("requests session-bound ICE configuration and recoverable live call state", async () => {
    vi.mocked(productJson)
      .mockResolvedValueOnce({ ice_servers: [], expires_at: "2026-08-22T18:10:00Z", ttl_seconds: 600 })
      .mockResolvedValueOnce({ call: activeVideoCall });

    await getIceServers();
    const recovered = await getLiveConversationCall("conversation-1");

    expect(productJson).toHaveBeenNthCalledWith(1, "calls/ice-servers");
    expect(productJson).toHaveBeenNthCalledWith(2, "conversations/conversation-1/call");
    expect(recovered?.id).toBe("call-1");
  });

  it("uses audio-only constraints for voice and audio/video constraints for video", () => {
    expect(mediaConstraints("VOICE")).toEqual({ audio: true, video: false });
    expect(mediaConstraints("VIDEO")).toEqual({ audio: true, video: true });
  });

  it("replaces only the active video sender when screen sharing starts", async () => {
    const replaceTrack = vi.fn(async () => undefined);
    const screenTrack = {
      kind: "video",
      addEventListener: vi.fn(),
      stop: vi.fn(),
    };
    const screenStream = {
      getVideoTracks: () => [screenTrack],
      getTracks: () => [screenTrack],
    } as unknown as MediaStream;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getDisplayMedia: vi.fn(async () => screenStream) },
    });

    const callbacks = {
      onCall: vi.fn(),
      onPhase: vi.fn(),
      onLocalStream: vi.fn(),
      onRemoteStream: vi.fn(),
      onMediaState: vi.fn(),
      onError: vi.fn(),
    };
    const client = { isLive: () => true, emit: vi.fn() };
    const controller = new WebRtcCallController(client as never, "user-1", callbacks);
    const internals = controller as unknown as {
      currentCall: CallSession | null;
      peer: { getSenders: () => Array<{ track: { kind: string }; replaceTrack: typeof replaceTrack }> } | null;
    };
    internals.currentCall = activeVideoCall;
    internals.peer = {
      getSenders: () => [{ track: { kind: "video" }, replaceTrack }],
    };

    await controller.startScreenShare();

    expect(navigator.mediaDevices.getDisplayMedia).toHaveBeenCalledWith({ video: true, audio: false });
    expect(replaceTrack).toHaveBeenCalledWith(screenTrack);
    expect(callbacks.onLocalStream).toHaveBeenCalledWith(screenStream);
    expect(callbacks.onMediaState).toHaveBeenLastCalledWith({
      muted: false,
      cameraOff: false,
      screenSharing: true,
    });
  });
});
