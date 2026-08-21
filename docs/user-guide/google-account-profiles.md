# Google Account Profiles

OpenJarvis supports named Google profile aliases so multiple Google accounts can
be connected, synced, and searched without overwriting each other's OAuth
tokens. Use aliases such as `personal`, `work`, `subscriptions`,
`kanakia-org-home`, or `banqer` to keep indexed data persona-scoped.

## Connect Profiles

Use `jarvis connect google` when you want one OAuth grant to cover Gmail, Drive,
Calendar, Contacts, and Tasks.

```bash
# Default Google profile
jarvis connect google

# Named profiles
jarvis connect google --account work
jarvis connect google --account personal
jarvis connect google --account subscriptions
```

The connector-specific commands use the same profile store and can also take an
account alias:

```bash
jarvis connect gmail --account work
jarvis connect gdrive --account research
jarvis connect gcalendar --account family
```

`--profile` is accepted as an alias for `--account`.

## Alias Names

Aliases should be short, readable, and stable. They are normalized to lowercase
safe filenames, so names such as `aquantive-nirav`, `kanakia.org-home`, and
`banqer` work. Windows-reserved names and trailing dots are rejected. Prefer
lowercase words separated by `-`, `_`, or `.`.

Avoid putting secrets in alias names. Aliases are used in local file paths,
document IDs, metadata, and source filters.

## Token Storage

Named profiles are stored under:

```text
~/.openjarvis/connectors/google/accounts/<alias>.json
```

Examples:

```text
~/.openjarvis/connectors/google/accounts/work.json
~/.openjarvis/connectors/google/accounts/personal.json
~/.openjarvis/connectors/google/accounts/banqer.json
```

The legacy single-profile token path is still read for compatibility:

```text
~/.openjarvis/connectors/google.json
```

## Migrating A Clean Install With One Existing Profile

If a machine already has one Google connection from before profile aliases,
choose the alias you want that account to become, explicitly remove the
unscoped legacy index rows/checkpoints, and reindex:

```bash
jarvis connect google --account work --migrate-legacy-google --sync
```

The migration flag is intentionally explicit because it deletes only legacy
Google rows whose metadata has no account alias. It preserves every already
named profile. Historical Gmail OAuth and Gmail IMAP rows both used
`source = "gmail"`; ambiguous unmarked Gmail rows are therefore preserved
instead of risking unrelated IMAP mail, while Gmail rows carrying positive
Google-connector provenance are migrated. Reindexing writes collision-safe IDs
and account metadata so future disconnects can remove exactly the selected
profile.

If you need to preserve the existing token without reauthenticating, copy the
legacy token into the new account directory:

```bash
mkdir -p ~/.openjarvis/connectors/google/accounts
cp ~/.openjarvis/connectors/google.json \
  ~/.openjarvis/connectors/google/accounts/work.json
```

After copying, run the same explicit migration and sync so indexed chunks
receive the account metadata:

```bash
jarvis connect google --account work --migrate-legacy-google --sync
```

## Analysis And Queries

Once profiles have synced, analysis works through the normal research and memory
tools. Each indexed chunk carries account metadata, and source lists expose both
plain connector IDs and scoped connector IDs:

```text
gmail
gmail:work
gdrive:research
gcalendar:family
```

Natural-language examples:

```bash
jarvis ask --account work "Summarize Gmail subscription renewals"
jarvis ask --account research "Find Drive files about the Q3 plan"
jarvis ask --accounts personal,work "Compare calendar conflicts this week"
```

`--account` is repeatable and `--accounts` accepts a comma-separated list. An
account filter implies `--research`, because the boundary applies to indexed
knowledge retrieval rather than direct model inference.

The research planner maps these requests to structured filters:

```python
search("subscription renewals", sources=["gmail"], accounts=["work"])
search("Q3 plan", sources=["gdrive"], accounts=["research"])
search("calendar conflicts", sources=["gcalendar"], accounts=["personal", "work"])
```

Direct retrieval can use either scoped source IDs or an account filter:

```python
store.retrieve("subscription renewals", source="gmail:work")
hybrid.search("Q3 plan", sources=["gdrive"], accounts=["research"])
```

Set a default research boundary and expand morning-digest Google sources across
selected profiles in `config.toml`:

```toml
[connectors.google.accounts.personal]
enabled = true

[connectors.google.accounts.work]
enabled = true

[agent]
default_accounts = ["personal"]

[digest]
accounts = ["personal", "work"]

[digest.messages]
sources = ["gmail", "google_tasks"]
```

An explicitly scoped source such as `gmail:research` is left unchanged. Without
`digest.accounts`, section sources keep their legacy default-profile behavior.
Google sync documents include the local alias, connector, and the
provider-asserted `source_email` claim delivered by Google's TLS token endpoint,
when available. The email is provenance for display and citation only; it is
not independently signature-validated and never controls authorization. The
local alias remains the retrieval boundary.

Setting a declared profile to `enabled = false` prevents new CLI/server use and
removes it from configured default research and digest account lists. Cleanup
remains available with `jarvis connect --account ALIAS --disconnect google` or
the provider-wide disconnect API, so disabling a profile never traps its
credentials or index. Unlisted ad-hoc aliases remain enabled for backwards
compatibility.

## UI And API Sync

The connector sync API accepts an optional `account` query parameter. Use the
real connector routes, not a synthetic `/v1/connectors/google/...` endpoint:

```text
POST /v1/connectors/gmail/sync?account=work
GET  /v1/connectors/gmail/sync?account=work
```

Sync status is tracked per connector/profile pair, so a long sync for
`gmail:work` does not mask the state of `gmail:personal`.

One named Google profile uses a shared OAuth grant for all five Google
connectors. Disconnecting any one of those connector routes for a named account
therefore disconnects the whole named Google profile and removes that account's
Gmail, Drive, Calendar, Contacts, and Tasks index rows together:

```text
POST /v1/connectors/gdrive/disconnect?account=work
```

This provider-wide behavior prevents half-disconnected profiles with stale
indexed data. Other named accounts are not affected.

## How To Test

For CLI and connector profile behavior:

```bash
uv run --extra dev pytest \
  tests/connectors/test_oauth_flow.py \
  tests/connectors/test_gmail.py \
  tests/connectors/test_store.py \
  tests/cli/test_connect.py
```

For analysis-layer account filters:

```bash
uv run --extra dev pytest \
  tests/agents/test_research_loop.py \
  tests/connectors/test_hybrid_search.py
```

For linting touched code:

```bash
uv run --extra dev ruff check \
  src/openjarvis/agents/research_loop.py \
  src/openjarvis/connectors/hybrid_search.py \
  src/openjarvis/server/connectors_router.py \
  tests/agents/test_research_loop.py \
  tests/connectors/test_hybrid_search.py
```
