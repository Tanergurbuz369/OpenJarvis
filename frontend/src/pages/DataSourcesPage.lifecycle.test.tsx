import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../lib/store', () => ({ useAppStore: vi.fn() }));

import {
  connectorInstanceKey,
  resolveConnectorAccount,
  SyncStatusDisplay,
} from './DataSourcesPage';
import type { SyncStatus } from '../types/connectors';
import type { CachedConnector } from '../lib/store';

const baseStatus: SyncStatus = {
  state: 'idle',
  items_synced: 0,
  items_total: 0,
  last_sync: null,
  error: null,
};

function renderStatus(sync: SyncStatus, disabled = false): string {
  return renderToStaticMarkup(
    <SyncStatusDisplay
      chunks={0}
      sync={sync}
      unitLabel="items"
      connectorId="obsidian"
      disabled={disabled}
      onSyncTriggered={vi.fn()}
    />,
  );
}

describe('connector lifecycle status', () => {
  it('renders pending cleanup without a competing sync action', () => {
    const html = renderStatus({ ...baseStatus, state: 'stopping' });

    expect(html).toContain('Disconnect pending');
    expect(html).toContain('cleaned up before this source disconnects');
    expect(html).not.toContain('<button');
  });

  it('disables sync while another connector lifecycle action is active', () => {
    const html = renderStatus(baseStatus, true);

    expect(html).toContain('Sync Now');
    expect(html).toMatch(/<button[^>]*disabled/);
  });

  it('selects and keys a named connected account without conflating defaults', () => {
    const connector: CachedConnector = {
      connector_id: 'gdrive',
      display_name: 'Google Drive',
      connected: false,
      chunks: 0,
      auth_type: 'oauth',
      accounts: [
        { account: 'disabled', connected: true, enabled: false },
        { account: 'work', connected: true, source_email: 'me@example.com' },
      ],
    };

    expect(resolveConnectorAccount(connector, undefined)).toBe('work');
    expect(resolveConnectorAccount(connector, ' Personal ')).toBe('personal');
    expect(connectorInstanceKey('gdrive', 'work')).toBe('gdrive:work');
    expect(connectorInstanceKey('gdrive')).toBe('gdrive');

    connector.accounts = [
      { account: 'disabled-work', connected: true, enabled: false },
    ];
    expect(resolveConnectorAccount(connector, undefined)).toBe('disabled-work');
  });
});
