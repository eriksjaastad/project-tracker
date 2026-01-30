import './WarningBanner.css';

export interface WarningBannerProps {
  message: string;
  type: 'error' | 'warning' | 'info';
  onDismiss: () => void;
  actionLabel?: string;
  onAction?: () => void;
}

export function WarningBanner({
  message,
  type,
  onDismiss,
  actionLabel,
  onAction,
}: WarningBannerProps) {
  return (
    <div className={`warning-banner warning-banner-${type}`} role="alert">
      <div className="warning-banner-message">{message}</div>
      <div className="warning-banner-actions">
        {actionLabel && onAction && (
          <button className="warning-banner-action" onClick={onAction} type="button">
            {actionLabel}
          </button>
        )}
        <button className="warning-banner-dismiss" onClick={onDismiss} type="button" aria-label="Dismiss">
          ×
        </button>
      </div>
    </div>
  );
}
