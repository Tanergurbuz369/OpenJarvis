import { describe, expect, it } from 'vitest';

import { shouldStartServerOAuth } from './SourceConnectFlow';
import type { ConnectResponse } from '../../types/connectors';

function response(
  patch: Partial<ConnectResponse> = {},
): ConnectResponse {
  return {
    connector_id: 'gdrive',
    connected: false,
    status: 'pending',
    ...patch,
  };
}

describe('setup connector OAuth decisions', () => {
  it('starts consent for an OAuth response that is still pending', () => {
    expect(shouldStartServerOAuth('oauth', response())).toBe(true);
  });

  it('starts consent whenever an OAuth response is not connected', () => {
    expect(
      shouldStartServerOAuth(
        'oauth',
        response({ status: 'disconnected', connected: false }),
      ),
    ).toBe(true);
  });

  it('does not replace a completed OAuth or non-OAuth connection with consent', () => {
    expect(
      shouldStartServerOAuth(
        'oauth',
        response({ status: 'connected', connected: true }),
      ),
    ).toBe(false);
    expect(shouldStartServerOAuth('token', response())).toBe(false);
  });

  it('honors an explicit oauth_required directive', () => {
    expect(
      shouldStartServerOAuth(
        'token',
        response({ status: 'oauth_required', oauth_start: '/oauth/start' }),
      ),
    ).toBe(true);
  });
});
