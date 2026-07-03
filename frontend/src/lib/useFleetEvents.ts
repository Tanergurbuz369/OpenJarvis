import { useEffect, useRef } from 'react';
import { getBase } from './api';
import type { AgentEvent } from './useAgentEvents';

const FLEET_EVENT_TYPES = [
  'fleet_mission_start',
  'fleet_mission_planned',
  'fleet_mission_end',
  'fleet_task_start',
  'fleet_task_end',
] as const;

function buildWsUrl(): string {
  const base = getBase();
  let origin: string;
  if (base) {
    origin = base.replace(/^http/, 'ws');
  } else {
    const loc = window.location;
    origin = `${loc.protocol === 'https:' ? 'wss:' : 'ws:'}//${loc.host}`;
  }
  return `${origin}/v1/agents/events`;
}

/**
 * Subscribe to fleet mission/subtask events over the shared agent-events
 * WebSocket (unfiltered connection; fleet events carry no agent_id).
 * Auto-reconnects with backoff when the socket drops.
 */
export function useFleetEvents(onEvent: (event: AgentEvent) => void): void {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (closed) return;
      try {
        ws = new WebSocket(buildWsUrl());
      } catch {
        schedule();
        return;
      }
      ws.onopen = () => {
        retry = 0;
      };
      ws.onmessage = (msg) => {
        try {
          const payload = JSON.parse(msg.data) as AgentEvent;
          if (!(FLEET_EVENT_TYPES as readonly string[]).includes(payload.type)) return;
          onEventRef.current(payload);
        } catch {
          // ignore malformed payload
        }
      };
      ws.onclose = () => {
        if (!closed) schedule();
      };
      ws.onerror = () => {
        ws?.close();
      };
    };

    const schedule = () => {
      if (closed) return;
      const delay = Math.min(30000, 1000 * 2 ** Math.min(retry, 5));
      retry += 1;
      reconnectTimer = setTimeout(connect, delay);
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);
}
