import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Network, Rocket, Search, XCircle } from 'lucide-react';
import {
  cancelFleetMission,
  createFleetMission,
  fetchFleetMission,
  fetchFleetMissions,
  fetchFleetRoles,
  fetchFleetStatus,
  type FleetMission,
  type FleetRole,
  type FleetStatus,
  type FleetSubtask,
} from '../lib/api';
import { useFleetEvents } from '../lib/useFleetEvents';

const STATUS_COLORS: Record<string, string> = {
  pending: 'var(--color-text-tertiary)',
  planning: 'var(--color-warning)',
  running: 'var(--color-accent)',
  completed: 'var(--color-success, #22c55e)',
  failed: 'var(--color-error)',
  canceled: 'var(--color-text-tertiary)',
  skipped: 'var(--color-text-tertiary)',
};

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] || 'var(--color-text-secondary)';
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium"
      style={{ color, border: `1px solid ${color}` }}
    >
      {(status === 'running' || status === 'planning') && (
        <span
          className="w-1.5 h-1.5 rounded-full animate-pulse"
          style={{ background: color }}
        />
      )}
      {status}
    </span>
  );
}

function SubtaskCard({ subtask, role }: { subtask: FleetSubtask; role?: FleetRole }) {
  const [expanded, setExpanded] = useState(false);
  const duration =
    subtask.started_at && subtask.finished_at
      ? `${(subtask.finished_at - subtask.started_at).toFixed(1)}s`
      : '';
  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-2"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        opacity: subtask.status === 'skipped' ? 0.6 : 1,
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xl shrink-0">{role?.icon || '🧩'}</span>
          <div className="min-w-0">
            <div
              className="text-sm font-medium truncate"
              style={{ color: 'var(--color-text)' }}
            >
              {role?.name || subtask.role_id}
            </div>
            <div
              className="text-xs truncate"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              {subtask.title}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {duration && (
            <span className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
              {duration}
            </span>
          )}
          <StatusBadge status={subtask.status} />
        </div>
      </div>
      {subtask.error && (
        <div className="text-xs" style={{ color: 'var(--color-error)' }}>
          {subtask.error}
        </div>
      )}
      {subtask.output && (
        <div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs cursor-pointer underline-offset-2 hover:underline"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            {expanded ? 'Hide output' : 'Show output'}
          </button>
          {expanded && (
            <pre
              className="mt-2 text-xs whitespace-pre-wrap max-h-64 overflow-y-auto rounded-lg p-3"
              style={{
                background: 'var(--color-bg-secondary)',
                color: 'var(--color-text-secondary)',
              }}
            >
              {subtask.output}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export function FleetPage() {
  const [status, setStatus] = useState<FleetStatus | null>(null);
  const [roles, setRoles] = useState<FleetRole[]>([]);
  const [missions, setMissions] = useState<FleetMission[]>([]);
  const [selected, setSelected] = useState<FleetMission | null>(null);
  const [objective, setObjective] = useState('');
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState('');
  const [roleQuery, setRoleQuery] = useState('');
  const [roleCategory, setRoleCategory] = useState('');
  const [showAllRoles, setShowAllRoles] = useState(false);

  const roleById = useMemo(() => {
    const map = new Map<string, FleetRole>();
    roles.forEach((r) => map.set(r.role_id, r));
    return map;
  }, [roles]);

  const refresh = useCallback(() => {
    fetchFleetStatus().then(setStatus).catch(() => {});
    fetchFleetMissions().then(setMissions).catch(() => {});
    setSelected((current) => {
      if (current) {
        fetchFleetMission(current.mission_id)
          .then((m) =>
            setSelected((latest) =>
              latest && latest.mission_id === m.mission_id ? m : latest,
            ),
          )
          .catch(() => {});
      }
      return current;
    });
  }, []);

  useEffect(() => {
    refresh();
    fetchFleetRoles().then(setRoles).catch(() => {});
  }, [refresh]);

  // Live updates over WebSocket; polling as a safety net while active.
  useFleetEvents(useCallback(() => refresh(), [refresh]));
  const missionActive =
    selected?.status === 'running' || selected?.status === 'planning';
  useEffect(() => {
    if (!missionActive) return;
    const interval = setInterval(refresh, 4000);
    return () => clearInterval(interval);
  }, [missionActive, refresh]);

  const handleLaunch = async () => {
    const text = objective.trim();
    if (!text || launching) return;
    setLaunching(true);
    setError('');
    try {
      const mission = await createFleetMission(text);
      setObjective('');
      setSelected(mission);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to launch mission');
    } finally {
      setLaunching(false);
    }
  };

  const openMission = (m: FleetMission) => {
    fetchFleetMission(m.mission_id).then(setSelected).catch(() => setSelected(m));
  };

  const filteredRoles = useMemo(() => {
    const q = roleQuery.trim().toLowerCase();
    let list = roles;
    if (roleCategory) list = list.filter((r) => r.category === roleCategory);
    if (q) {
      list = list.filter((r) =>
        `${r.role_id} ${r.name} ${r.description} ${r.keywords.join(' ')}`
          .toLowerCase()
          .includes(q),
      );
    }
    return list;
  }, [roles, roleQuery, roleCategory]);

  const visibleRoles = showAllRoles ? filteredRoles : filteredRoles.slice(0, 24);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-10">
      <div className="max-w-4xl mx-auto w-full flex flex-col gap-8">
        {/* Header */}
        <header>
          <div className="flex items-center gap-3">
            <Network size={20} style={{ color: 'var(--color-accent)' }} />
            <h1 className="text-lg font-semibold" style={{ color: 'var(--color-text)' }}>
              Agent Fleet
            </h1>
            {status && (
              <span className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                {status.roles} specialists · {status.missions_active} active mission
                {status.missions_active === 1 ? '' : 's'}
              </span>
            )}
          </div>
          <p className="text-sm mt-2 max-w-2xl" style={{ color: 'var(--color-text-secondary)' }}>
            Give the fleet an objective. A planner splits it into subtasks, the
            best-suited specialists activate automatically, work in parallel, and a
            chief of staff merges everything into one deliverable — all on your
            local model.
          </p>
        </header>

        {/* Mission composer */}
        <section
          className="rounded-xl p-4 flex flex-col gap-3"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        >
          <textarea
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleLaunch();
            }}
            placeholder="e.g. Research the local-AI market, draft a launch blog post, and propose a pricing model for my app…"
            rows={3}
            className="w-full resize-none rounded-lg p-3 text-sm outline-none"
            style={{
              background: 'var(--color-bg-secondary)',
              color: 'var(--color-text)',
              border: '1px solid var(--color-border)',
            }}
          />
          <div className="flex items-center justify-between">
            <span className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
              ⌘/Ctrl+Enter to launch
            </span>
            <button
              onClick={handleLaunch}
              disabled={launching || !objective.trim()}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ background: 'var(--color-accent)', color: 'white' }}
            >
              {launching ? <Loader2 size={14} className="animate-spin" /> : <Rocket size={14} />}
              Launch Mission
            </button>
          </div>
          {error && (
            <div className="text-xs" style={{ color: 'var(--color-error)' }}>
              {error}
            </div>
          )}
        </section>

        {/* Selected mission */}
        {selected && (
          <section className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <h2
                  className="text-sm font-semibold truncate"
                  style={{ color: 'var(--color-text)' }}
                >
                  {selected.objective}
                </h2>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <StatusBadge status={selected.status} />
                {(selected.status === 'running' || selected.status === 'planning') && (
                  <button
                    onClick={() =>
                      cancelFleetMission(selected.mission_id).then(refresh).catch(() => {})
                    }
                    className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs cursor-pointer"
                    style={{
                      color: 'var(--color-error)',
                      border: '1px solid var(--color-error)',
                    }}
                  >
                    <XCircle size={12} /> Cancel
                  </button>
                )}
              </div>
            </div>

            {selected.status === 'planning' && (
              <div
                className="text-sm flex items-center gap-2"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                <Loader2 size={14} className="animate-spin" />
                Mission planner is splitting the objective into subtasks…
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {(selected.subtasks || []).map((st) => (
                <SubtaskCard key={st.subtask_id} subtask={st} role={roleById.get(st.role_id)} />
              ))}
            </div>

            {selected.final_output && (
              <div
                className="rounded-xl p-4"
                style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
              >
                <div className="text-xs font-semibold mb-2 flex items-center gap-2" style={{ color: 'var(--color-text-secondary)' }}>
                  🎩 Final deliverable
                </div>
                <pre
                  className="text-sm whitespace-pre-wrap"
                  style={{ color: 'var(--color-text)', fontFamily: 'inherit' }}
                >
                  {selected.final_output}
                </pre>
              </div>
            )}
            {selected.error && (
              <div className="text-xs" style={{ color: 'var(--color-error)' }}>
                {selected.error}
              </div>
            )}
          </section>
        )}

        {/* Mission history */}
        {missions.length > 0 && (
          <section>
            <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text)' }}>
              Missions
            </h2>
            <div className="flex flex-col gap-2">
              {missions.map((m) => (
                <button
                  key={m.mission_id}
                  onClick={() => openMission(m)}
                  className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-left cursor-pointer transition-colors"
                  style={{
                    background:
                      selected?.mission_id === m.mission_id
                        ? 'var(--color-bg-tertiary)'
                        : 'var(--color-bg-secondary)',
                    border: '1px solid var(--color-border)',
                  }}
                >
                  <span
                    className="text-sm truncate"
                    style={{ color: 'var(--color-text)' }}
                  >
                    {m.objective}
                  </span>
                  <span className="flex items-center gap-2 shrink-0">
                    <span className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                      {m.subtask_count} task{m.subtask_count === 1 ? '' : 's'}
                    </span>
                    <StatusBadge status={m.status} />
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Role catalog */}
        <section>
          <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
            <h2 className="text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
              Specialist Catalog{' '}
              <span style={{ color: 'var(--color-text-tertiary)' }}>({filteredRoles.length})</span>
            </h2>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search
                  size={13}
                  className="absolute left-2.5 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--color-text-tertiary)' }}
                />
                <input
                  value={roleQuery}
                  onChange={(e) => setRoleQuery(e.target.value)}
                  placeholder="Search specialists…"
                  className="pl-8 pr-3 py-1.5 rounded-lg text-xs outline-none w-48"
                  style={{
                    background: 'var(--color-bg-secondary)',
                    color: 'var(--color-text)',
                    border: '1px solid var(--color-border)',
                  }}
                />
              </div>
            </div>
          </div>
          <div className="flex gap-1.5 flex-wrap mb-3">
            <button
              onClick={() => setRoleCategory('')}
              className="px-2.5 py-1 rounded-full text-[11px] cursor-pointer"
              style={{
                background: roleCategory === '' ? 'var(--color-accent)' : 'var(--color-bg-secondary)',
                color: roleCategory === '' ? 'white' : 'var(--color-text-secondary)',
                border: '1px solid var(--color-border)',
              }}
            >
              all
            </button>
            {(status?.categories || []).map((cat) => (
              <button
                key={cat}
                onClick={() => setRoleCategory(cat === roleCategory ? '' : cat)}
                className="px-2.5 py-1 rounded-full text-[11px] cursor-pointer"
                style={{
                  background: roleCategory === cat ? 'var(--color-accent)' : 'var(--color-bg-secondary)',
                  color: roleCategory === cat ? 'white' : 'var(--color-text-secondary)',
                  border: '1px solid var(--color-border)',
                }}
              >
                {cat}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {visibleRoles.map((role) => (
              <div
                key={role.role_id}
                title={role.description}
                className="flex items-center gap-2 rounded-lg px-3 py-2"
                style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
              >
                <span className="text-lg shrink-0">{role.icon}</span>
                <div className="min-w-0">
                  <div className="text-xs font-medium truncate" style={{ color: 'var(--color-text)' }}>
                    {role.name}
                  </div>
                  <div className="text-[10px] truncate" style={{ color: 'var(--color-text-tertiary)' }}>
                    {role.category}
                    {role.tools.length > 0 && ` · ${role.tools.length} tools`}
                  </div>
                </div>
              </div>
            ))}
          </div>
          {filteredRoles.length > 24 && (
            <button
              onClick={() => setShowAllRoles(!showAllRoles)}
              className="mt-3 text-xs cursor-pointer underline-offset-2 hover:underline"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              {showAllRoles ? 'Show less' : `Show all ${filteredRoles.length} specialists`}
            </button>
          )}
        </section>
      </div>
    </div>
  );
}
