/**
 * ProgressIndicator — compact progress bar with "N/M stages" label.
 *
 * Props:
 *  - completedCount: number of completed stages
 *  - totalCount: total number of stages
 */
export default function ProgressIndicator({ completedCount, totalCount }) {
  if (totalCount === 0) return null;

  const pct = Math.round((completedCount / totalCount) * 100);

  return (
    <div className="progress-indicator" role="progressbar" aria-valuenow={completedCount} aria-valuemin={0} aria-valuemax={totalCount} aria-label={`${completedCount} of ${totalCount} stages complete`}>
      <span className="progress-indicator-label">
        {completedCount}/{totalCount} stages
      </span>
      <div className="progress-indicator-track">
        <div
          className="progress-indicator-fill"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
