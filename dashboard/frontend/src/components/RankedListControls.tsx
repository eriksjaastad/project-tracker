import './RankedListControls.css';

// The API returns open listings already ranked by fit (#101679546294759424):
// `fresh` (posted within 30 days) and `stale`. The page shows the top
// TOP_LISTINGS fresh ones and offers controls to widen; nothing is deleted.
export const TOP_LISTINGS = 25;

interface Props {
  shownCount: number;
  visibleCount: number;
  staleCount: number;
  showStale: boolean;
  onToggleStale: () => void;
  onShowAll: () => void;
}

export function RankedListControls({
  shownCount, visibleCount, staleCount, showStale, onToggleStale, onShowAll,
}: Props) {
  if (staleCount === 0 && shownCount >= visibleCount) {
    return null;
  }
  return (
    <div className="ranked-list-controls">
      {shownCount < visibleCount && (
        <button type="button" className="ranked-list-btn" onClick={onShowAll}>
          Show all {visibleCount}
        </button>
      )}
      {staleCount > 0 && (
        <>
          {!showStale && (
            <span className="ranked-list-note">
              {staleCount} older {staleCount === 1 ? 'listing' : 'listings'} hidden
            </span>
          )}
          <button type="button" className="ranked-list-btn" onClick={onToggleStale}>
            {showStale ? 'Hide older listings' : 'Show older listings'}
          </button>
        </>
      )}
    </div>
  );
}
