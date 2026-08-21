import { useEffect, useState } from 'react';
import type { ConnectorInfo } from '../types/connectors';

const GOOGLE_CONNECTORS = new Set([
  'gmail',
  'gdrive',
  'gcalendar',
  'gcontacts',
  'google_tasks',
]);

export function supportsGoogleAccounts(connectorId: string): boolean {
  return GOOGLE_CONNECTORS.has(connectorId);
}

export function normalizeGoogleAccount(account: string): string {
  return account.trim().toLowerCase();
}

export function canSelectGoogleAccountProfile(
  accounts: NonNullable<ConnectorInfo['accounts']>,
  account: string,
): boolean {
  const normalized = normalizeGoogleAccount(account);
  const profile = accounts.find(
    (candidate) => normalizeGoogleAccount(candidate.account) === normalized,
  );
  // A disabled profile cannot be connected or synced, but an existing
  // connection must remain selectable so the user can disconnect/clean it.
  return !profile || profile.enabled !== false || profile.connected;
}

export function GoogleAccountField({
  connectorId,
  account,
  accounts = [],
  disabled = false,
  onChange,
}: {
  connectorId: string;
  account: string;
  accounts?: NonNullable<ConnectorInfo['accounts']>;
  disabled?: boolean;
  onChange: (account: string) => void;
}) {
  const listId = `google-account-${connectorId.replace(/[^a-z0-9_-]/gi, '-')}`;
  const [draft, setDraft] = useState(account);

  useEffect(() => setDraft(account), [account]);

  const normalizedDraft = normalizeGoogleAccount(draft);
  const disabledProfile = accounts.find(
    (profile) =>
      profile.account.toLowerCase() === normalizedDraft && profile.enabled === false,
  );
  const commit = () => {
    if (canSelectGoogleAccountProfile(accounts, normalizedDraft)) {
      onChange(normalizedDraft);
    }
  };
  const profileBlocked = !canSelectGoogleAccountProfile(accounts, normalizedDraft);

  return (
    <div style={{ marginBottom: 10 }}>
      <label
        htmlFor={listId}
        style={{
          display: 'block',
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--color-text-secondary)',
          marginBottom: 4,
        }}
      >
        Google account profile
      </label>
      <input
        id={listId}
        list={`${listId}-options`}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            commit();
          }
        }}
        disabled={disabled}
        placeholder="Profile name (for example, work)"
        autoComplete="off"
        style={{
          width: '100%',
          padding: '7px 10px',
          background: 'var(--color-bg)',
          border: '1px solid var(--color-border)',
          borderRadius: 4,
          color: 'var(--color-text)',
          fontSize: 12,
          boxSizing: 'border-box',
          opacity: disabled ? 0.6 : 1,
        }}
      />
      <datalist id={`${listId}-options`}>
        {accounts.map((profile) => (
          <option
            key={profile.account}
            value={profile.account}
            disabled={profile.enabled === false && !profile.connected}
          >
            {profile.source_email || (profile.connected ? 'Connected' : 'Not connected')}
          </option>
        ))}
      </datalist>
      {draft.trim() !== account && (
        <button
          type="button"
          onClick={commit}
          disabled={disabled || profileBlocked}
          style={{
            marginTop: 5,
            padding: '4px 8px',
            background: 'var(--color-accent-purple)',
            border: 'none',
            borderRadius: 4,
            color: 'var(--color-on-accent)',
            fontSize: 10.5,
            cursor: disabled || profileBlocked ? 'default' : 'pointer',
          }}
        >
          Use profile
        </button>
      )}
      <div
        style={{
          marginTop: 4,
          fontSize: 10.5,
          color: 'var(--color-text-tertiary)',
        }}
      >
        {account
          ? `Actions apply only to “${account}”.`
          : 'Leave blank to use the legacy default Google connection.'}
      </div>
      {disabledProfile && (
        <div role="alert" style={{ marginTop: 4, fontSize: 10.5, color: '#f59e0b' }}>
          This profile is disabled in config.toml.
        </div>
      )}
      {accounts.length > 0 && (
        <div
          data-testid="known-google-accounts"
          style={{
            marginTop: 4,
            fontSize: 10.5,
            color: 'var(--color-text-tertiary)',
          }}
        >
          Known profiles:{' '}
          {accounts
            .map((profile) =>
              profile.source_email
                ? `${profile.account} (${profile.source_email})${
                    profile.enabled === false ? ' — disabled' : ''
                  }`
                : `${profile.account}${profile.enabled === false ? ' — disabled' : ''}`,
            )
            .join(', ')}
        </div>
      )}
    </div>
  );
}
