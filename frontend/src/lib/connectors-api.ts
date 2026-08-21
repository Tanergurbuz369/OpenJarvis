import { apiFetch, getBase } from './api';
import type { ConnectorInfo, SyncStatus, ConnectRequest, ConnectResponse } from '../types/connectors';

// ---------------------------------------------------------------------------
// Connectors API
// ---------------------------------------------------------------------------
//
// Every call here must go through apiFetch() (not a bare fetch()) so the
// Bearer auth header is attached when OPENJARVIS_API_KEY is set -- direct
// fetch() calls silently 401 against an authenticated server, exactly the
// bug apiFetch was introduced to prevent elsewhere (#266). This file was
// missed when that fix landed.

export async function listConnectors(): Promise<ConnectorInfo[]> {
  const res = await apiFetch('/v1/connectors');
  if (!res.ok) throw new Error(`Failed to list connectors: ${res.status}`);
  const data = await res.json();
  return data.connectors || [];
}

export async function getConnector(id: string, account = ''): Promise<ConnectorInfo> {
  const query = account ? `?account=${encodeURIComponent(account)}` : '';
  const res = await apiFetch(`/v1/connectors/${encodeURIComponent(id)}${query}`);
  if (!res.ok) throw new Error(`Failed to get connector ${id}: ${res.status}`);
  return res.json();
}

export async function connectSource(id: string, req: ConnectRequest): Promise<ConnectResponse> {
  const res = await apiFetch(`/v1/connectors/${encodeURIComponent(id)}/connect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    // Surface the backend's actionable detail (e.g. malformed Client ID /
    // Secret) instead of a bare status code so the UI can render it.
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Failed to connect ${id}: ${res.status}`);
  }
  return res.json();
}

const OAUTH_POPUP_FEATURES = 'width=600,height=700';

/** Open a placeholder while the caller still owns a trusted click gesture.
 * Browsers may block a popup created only after an awaited API request. */
export function openServerOAuthPopup(): Window | null {
  return window.open('about:blank', '_blank', OAUTH_POPUP_FEATURES);
}

/** Open the server-side OAuth consent flow in a popup and resolve once the
 *  connector reports connected (or reject on timeout). Reused for any OAuth
 *  connector whose /connect returned `oauth_required` (issue #512). */
export async function startServerOAuth(
  id: string,
  oauthStartPath?: string,
  existingPopup?: Window | null,
  requestedAccount = '',
): Promise<void> {
  const popup = existingPopup ?? openServerOAuthPopup();
  if (!popup) {
    throw new Error('Authorization popup was blocked — allow popups and retry.');
  }
  const path = oauthStartPath || `/v1/connectors/${encodeURIComponent(id)}/oauth/start`;
  const startUrl = new URL(`${getBase()}${path}`, window.location.origin);
  if (requestedAccount && !startUrl.searchParams.has('account')) {
    startUrl.searchParams.set('account', requestedAccount);
  }
  const account = startUrl.searchParams.get('account') || '';
  startUrl.searchParams.set('response_mode', 'json');

  try {
    const startResponse = await apiFetch(`${startUrl.pathname}${startUrl.search}`);
    if (!startResponse.ok) {
      const err = await startResponse.json().catch(() => ({ detail: startResponse.statusText }));
      throw new Error(err.detail || `Failed to start OAuth: ${startResponse.status}`);
    }
    const payload = (await startResponse.json()) as { authorization_url?: string };
    if (!payload.authorization_url) {
      throw new Error('OAuth start returned no authorization URL');
    }
    popup.location.href = payload.authorization_url;
  } catch (error) {
    popup.close();
    throw error;
  }

  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const info = await getConnector(id, account);
        if (info.connected) {
          clearInterval(interval);
          clearTimeout(timer);
          resolve();
        }
      } catch {
        // ignore transient polling errors
      }
    }, 2000);
    const timer = setTimeout(() => {
      clearInterval(interval);
      popup.close();
      reject(new Error('Authorization timed out — please try again.'));
    }, 180000);
  });
}

export class ConnectorApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ConnectorApiError';
  }
}

export async function disconnectSource(
  id: string,
  signal?: AbortSignal,
  account = '',
): Promise<void> {
  const query = account ? `?account=${encodeURIComponent(account)}` : '';
  const res = await apiFetch(`/v1/connectors/${encodeURIComponent(id)}/disconnect${query}`, {
    method: 'POST',
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ConnectorApiError(
      err.detail || `Failed to disconnect ${id}: ${res.status}`,
      res.status,
    );
  }
}

export interface DisconnectUntilCompleteOptions {
  signal?: AbortSignal;
  retryDelayMs?: number;
  onPending?: (message: string) => void;
  account?: string;
}

function waitForDisconnectRetry(delayMs: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Disconnect cancelled', 'AbortError'));
      return;
    }

    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', handleAbort);
      resolve();
    }, delayMs);
    const handleAbort = () => {
      clearTimeout(timer);
      reject(new DOMException('Disconnect cancelled', 'AbortError'));
    };
    signal?.addEventListener('abort', handleAbort, { once: true });
  });
}

/**
 * Finish a disconnect even when the backend first returns 409 while an active
 * sync is stopping. The server deliberately keeps credentials and indexed
 * data intact until that worker exits; retrying is what completes cleanup.
 */
export async function disconnectSourceUntilComplete(
  id: string,
  {
    signal,
    retryDelayMs = 1500,
    onPending,
    account = '',
  }: DisconnectUntilCompleteOptions = {},
): Promise<void> {
  while (true) {
    try {
      await disconnectSource(id, signal, account);
      return;
    } catch (err) {
      if (!(err instanceof ConnectorApiError) || err.status !== 409) {
        throw err;
      }
      onPending?.(err.message);
      await waitForDisconnectRetry(retryDelayMs, signal);
    }
  }
}

export async function getSyncStatus(id: string, account = ''): Promise<SyncStatus> {
  const query = account ? `?account=${encodeURIComponent(account)}` : '';
  const res = await apiFetch(`/v1/connectors/${encodeURIComponent(id)}/sync${query}`);
  if (!res.ok) throw new Error(`Failed to get sync status for ${id}: ${res.status}`);
  return res.json();
}

export async function triggerSync(id: string, account = ''): Promise<{ connector_id: string; chunks_indexed: number; status: string }> {
  const query = account ? `?account=${encodeURIComponent(account)}` : '';
  const res = await apiFetch(`/v1/connectors/${encodeURIComponent(id)}/sync${query}`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Sync failed: ${res.status}`);
  }
  return res.json();
}
