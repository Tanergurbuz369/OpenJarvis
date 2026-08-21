import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { GoogleAccountField, supportsGoogleAccounts } from './GoogleAccountField';

describe('Google account profile field', () => {
  it('renders known aliases and verified source-email provenance', () => {
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

  it('marks configured disabled profiles as unavailable', () => {
    const html = renderToStaticMarkup(
      <GoogleAccountField
        connectorId="gmail"
        account="work"
        accounts={[{ account: 'work', connected: true, enabled: false }]}
        onChange={vi.fn()}
      />,
    );

    expect(html).toContain('disabled in config.toml');
    expect(html).toMatch(/<option[^>]*disabled/);
    expect(html).toContain('work — disabled');
  });
});
