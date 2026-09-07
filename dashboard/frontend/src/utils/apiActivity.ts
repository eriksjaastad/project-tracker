export interface Usage {
  provider: string;
  service?: string;
  model?: string;
  project: string;
  timestamp: string;
  estimated_cost_usd: number | string | null;
}

export interface Activity {
  provider: string;
  service: string;
  project: string;
  calls: number;
  cost: number;
  unpriced: boolean;
  lastSeen: string;
}

export function summarizeActivity(rows: Usage[], day: string): Activity[] {
  const start = new Date(`${day}T00:00:00`);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  const groups = new Map<string, Activity>();
  for (const row of rows) {
    const timestamp = new Date(row.timestamp).getTime();
    if (!Number.isFinite(timestamp) || timestamp < start.getTime() || timestamp >= end.getTime()) continue;
    const provider = row.provider || 'Unknown provider';
    const service = row.service || row.model || 'Unspecified API';
    const project = row.project || 'Unattributed';
    const key = JSON.stringify([provider, service, project]);
    const group = groups.get(key) || { provider, service, project, calls: 0, cost: 0, unpriced: false, lastSeen: row.timestamp };
    group.calls += 1;
    const rawCost = row.estimated_cost_usd;
    const cost = typeof rawCost === 'number' ? rawCost
      : typeof rawCost === 'string' && rawCost.trim() ? Number(rawCost) : NaN;
    if (!Number.isFinite(cost)) group.unpriced = true;
    else group.cost += cost;
    if (timestamp > new Date(group.lastSeen).getTime()) group.lastSeen = row.timestamp;
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => new Date(b.lastSeen).getTime() - new Date(a.lastSeen).getTime());
}
