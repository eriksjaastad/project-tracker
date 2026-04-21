export const GROUP_TITLES: Record<string, string> = {
  AP: 'Auxesis Projects',
  AI: 'Auxesis Incubators',
};

export interface PortfolioGroup<T extends { portfolio_group?: string | null }> {
  key: string;
  title: string;
  projects: T[];
}

export function groupByPortfolio<T extends { portfolio_group?: string | null }>(
  projects: T[]
): PortfolioGroup<T>[] {
  const grouped = new Map<string, T[]>();
  for (const project of projects) {
    const key = project.portfolio_group || 'default';
    const existing = grouped.get(key) || [];
    existing.push(project);
    grouped.set(key, existing);
  }

  const orderedKeys = [
    ...Object.keys(GROUP_TITLES).filter((key) => grouped.has(key)),
    ...Array.from(grouped.keys()).filter(
      (key) => key !== 'default' && !(key in GROUP_TITLES)
    ),
  ];
  if (grouped.has('default')) {
    orderedKeys.push('default');
  }

  return orderedKeys.map((key) => ({
    key,
    title: GROUP_TITLES[key] || 'Other Projects',
    projects: grouped.get(key) || [],
  }));
}
