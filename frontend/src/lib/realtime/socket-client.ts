import { requestRealtimeTicket } from "@/lib/api/communication";

export type RealtimeState = "connecting" | "live" | "fallback";

export interface RealtimeEventHandlers {
  onState: (state: RealtimeState) => void;
  onEvent: (event: string, payload: unknown) => void;
}

type PendingAck = {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
  timeout: number;
};

const ACK_TIMEOUT_MS = 7000;
const RECONNECT_DELAY_MS = 1800;
const HEARTBEAT_INTERVAL_MS = 20000;

function websocketUrl(baseUrl: string): string {
  const url = new URL("/socket.io/", baseUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("EIO", "4");
  url.searchParams.set("transport", "websocket");
  return url.toString();
}

function parseAckPacket(packet: string): { id: number; value: unknown } | null {
  if (!packet.startsWith("43")) return null;
  let cursor = 2;
  while (cursor < packet.length && /\d/.test(packet[cursor] ?? "")) cursor += 1;
  if (cursor === 2) return null;
  const id = Number(packet.slice(2, cursor));
  const values = JSON.parse(packet.slice(cursor)) as unknown[];
  return { id, value: values[0] };
}

function parseEventPacket(packet: string): { event: string; payload: unknown } | null {
  if (!packet.startsWith("42")) return null;
  let cursor = 2;
  while (cursor < packet.length && /\d/.test(packet[cursor] ?? "")) cursor += 1;
  const values = JSON.parse(packet.slice(cursor)) as unknown[];
  const event = values[0];
  if (typeof event !== "string") return null;
  return { event, payload: values[1] };
}

export function configuredRealtimeUrl(): string | null {
  const value = process.env.NEXT_PUBLIC_REALTIME_URL?.trim();
  return value || null;
}

export class RealtimeSocketClient {
  private socket: WebSocket | null = null;
  private stopped = false;
  private live = false;
  private ackId = 0;
  private pendingAcks = new Map<number, PendingAck>();
  private reconnectTimer: number | null = null;
  private heartbeatTimer: number | null = null;

  constructor(
    private readonly baseUrl: string,
    private readonly conversationId: string,
    private readonly handlers: RealtimeEventHandlers,
  ) {}

  start(): void {
    this.stopped = false;
    void this.connect();
  }

  stop(): void {
    this.stopped = true;
    this.live = false;
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer);
    if (this.heartbeatTimer !== null) window.clearInterval(this.heartbeatTimer);
    this.reconnectTimer = null;
    this.heartbeatTimer = null;
    this.rejectPending(new Error("Realtime connection stopped."));
    this.socket?.close();
    this.socket = null;
  }

  isLive(): boolean {
    return this.live && this.socket?.readyState === WebSocket.OPEN;
  }

  async emit<T>(event: string, payload: Record<string, unknown>): Promise<T> {
    const socket = this.socket;
    if (!this.live || !socket || socket.readyState !== WebSocket.OPEN) {
      throw new Error("Realtime connection is not live.");
    }
    const id = ++this.ackId;
    return new Promise<T>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        this.pendingAcks.delete(id);
        reject(new Error(`Realtime ${event} acknowledgment timed out.`));
      }, ACK_TIMEOUT_MS);
      this.pendingAcks.set(id, {
        resolve: (value) => resolve(value as T),
        reject,
        timeout,
      });
      socket.send(`42${id}${JSON.stringify([event, payload])}`);
    });
  }

  private async connect(): Promise<void> {
    if (this.stopped) return;
    this.handlers.onState("connecting");
    try {
      const ticket = await requestRealtimeTicket();
      if (this.stopped) return;
      const socket = new WebSocket(websocketUrl(this.baseUrl));
      this.socket = socket;
      socket.addEventListener("message", (event) => this.handlePacket(String(event.data), ticket.token));
      socket.addEventListener("close", () => this.handleClose());
      socket.addEventListener("error", () => {
        if (!this.live) this.handlers.onState("fallback");
      });
    } catch {
      this.handlers.onState("fallback");
      this.scheduleReconnect();
    }
  }

  private handlePacket(packet: string, ticket: string): void {
    const socket = this.socket;
    if (!socket) return;

    if (packet.startsWith("0")) {
      socket.send(`40${JSON.stringify({ token: ticket })}`);
      return;
    }
    if (packet === "2") {
      socket.send("3");
      return;
    }
    if (packet.startsWith("40")) {
      this.live = true;
      this.handlers.onState("live");
      void this.emit<{ ok: boolean }>("conversation.join", {
        conversation_id: this.conversationId,
      })
        .then((result) => {
          if (!result.ok) socket.close();
        })
        .catch(() => {
          socket.close();
        });
      if (this.heartbeatTimer !== null) window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = window.setInterval(() => {
        if (!this.isLive()) return;
        void this.emit("presence.heartbeat", {}).catch(() => undefined);
      }, HEARTBEAT_INTERVAL_MS);
      return;
    }
    if (packet.startsWith("44") || packet === "41" || packet === "1") {
      socket.close();
      return;
    }

    try {
      const ack = parseAckPacket(packet);
      if (ack) {
        const pending = this.pendingAcks.get(ack.id);
        if (!pending) return;
        window.clearTimeout(pending.timeout);
        this.pendingAcks.delete(ack.id);
        pending.resolve(ack.value);
        return;
      }
      const event = parseEventPacket(packet);
      if (event) this.handlers.onEvent(event.event, event.payload);
    } catch {
      // Malformed or unsupported packets are ignored; REST cursor recovery remains authoritative.
    }
  }

  private handleClose(): void {
    this.live = false;
    if (this.heartbeatTimer !== null) window.clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
    this.rejectPending(new Error("Realtime connection closed before acknowledgment."));
    if (this.stopped) return;
    this.handlers.onState("fallback");
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.reconnectTimer !== null) return;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      void this.connect();
    }, RECONNECT_DELAY_MS);
  }

  private rejectPending(reason: Error): void {
    for (const pending of this.pendingAcks.values()) {
      window.clearTimeout(pending.timeout);
      pending.reject(reason);
    }
    this.pendingAcks.clear();
  }
}
