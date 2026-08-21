import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import {
  canSelectGoogleAccountProfile,
  GoogleAccountField,
  normalizeGoogleAccount,
  supportsGoogleAccounts,
} from './GoogleAccountField';

describe('Google account profile field', () => {
  it('renders known aliases and provider-asserted source-email provenance', () => {
    const html = renderToStaticMarkup(
      <GoogleAccountField
        connectorId="gdrive"
        account="work"
        accounts={[
          {
            account: 'work',
            connected: true,
            source_email: 'person@company.example',
          },
          { account: 'personal', connected: false },
        ]}
        onChange={vi.fn()}
      />,
    );

    expect(html).toContain('Google account profile');
    expect(html).toContain('value="work"');
    expect(html).toContain('value="personal"');
    expect(html).toContain('person@company.example');
    expect(html).toContain('Actions apply only to');
  });

  it('only enables named profiles for Google provider connectors', () => {
    expect(supportsGoogleAccounts('gmail')).toBe(true);
    expect(supportsGoogleAccounts('google_tasks')).toBe(true);
    expect(supportsGoogleAccounts('spotify')).toBe(false);
    expect(supportsGoogleAccounts('gmail_imap')).toBe(false);
  });

  it('normalizes aliases before they reach connector lifecycle state', () => {
    expect(normalizeGoogleAccount(' Work ')).toBe('work');
  });

  it('keeps disabled connected profiles selectable only for cleanup', () => {
    const accounts = [
      { account: 'work', connected: true, enabled: true },
      { account: 'personal', connected: true, enabled: false },
      { account: 'archived', connected: false, enabled: false },
    ];
    expect(canSelectGoogleAccountProfile(accounts, 'personal')).toBe(true);
    expect(canSelectGoogleAccountProfile(accounts, 'archived')).toBe(false);

    const html = renderToStaticMarkup(
      <GoogleAccountField
        connectorId="gmail"
        account="work"
        accounts={accounts}
        onChange={vi.fn()}
      />,
    );

    expect(html).toMatch(/<option value="personal">/);
    expect(html).toMatch(/<option value="archived" disabled/);
    expect(html).toContain('personal — disabled');
  });
});
