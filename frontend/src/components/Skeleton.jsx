export function SkeletonCard() {
  return (
    <div className="skeleton-card">
      <div className="skeleton-line skeleton-line--title" />
      <div className="skeleton-line skeleton-line--text" />
      <div className="skeleton-line skeleton-line--text skeleton-line--short" />
    </div>
  );
}

export function SkeletonStat() {
  return (
    <div className="stat-card skeleton-stat">
      <div className="skeleton-line skeleton-line--title" />
      <div className="skeleton-line skeleton-line--short" />
    </div>
  );
}

export function SkeletonFilterTabs() {
  return (
    <div className="filter-tabs">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="skeleton-line skeleton-tab-pill" />
      ))}
    </div>
  );
}
