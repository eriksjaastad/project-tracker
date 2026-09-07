import { useEffect, useState } from 'react';
import { isAbortError } from '../api';
import './LoopMonitor.css';

interface LoopStatus {
    loop: string;
    health: 'healthy' | 'warning' | 'overdue' | 'failed' | 'never_run';
    health_icon: string;
    last_run: string | null;
    last_run_human: string;
    status: string;
    cards_created: number;
    duration_seconds: number | null;
    error: string | null;
}

interface LoopMonitorProps {
    refreshInterval?: number; // in milliseconds
}

export function LoopMonitor({ refreshInterval = 60000 }: LoopMonitorProps) {
    const [loops, setLoops] = useState<LoopStatus[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchLoopStatus = async (signal?: AbortSignal) => {
        try {
            const response = await fetch('/api/loops', { signal });
            if (!response.ok) throw new Error('Failed to fetch loop status');
            const data = await response.json();
            setLoops(data.loops);
            setError(null);
        } catch (err) {
            if (isAbortError(err)) {
                return;
            }
            setError(err instanceof Error ? err.message : 'Unknown error');
        } finally {
            if (!signal?.aborted) setLoading(false);
        }
    };

    useEffect(() => {
        // Each tick gets its own controller, and every one is held until it
        // settles. Keeping only the latest would orphan any earlier request
        // still in flight when the next tick starts: cleanup could no longer
        // abort it, and it would setState after unmount — the exact bug this
        // card exists to close.
        const inFlight = new Set<AbortController>();
        const run = async () => {
            const controller = new AbortController();
            inFlight.add(controller);
            try {
                await fetchLoopStatus(controller.signal);
            } finally {
                inFlight.delete(controller);
            }
        };
        void run();
        const interval = setInterval(() => void run(), refreshInterval);
        return () => {
            clearInterval(interval);
            inFlight.forEach(controller => controller.abort());
            inFlight.clear();
        };
    }, [refreshInterval]);

    if (loading) {
        return (
            <div className="loop-monitor loading">
                <div className="loop-monitor-header">
                    <h2>🤖 Autonomous Loops</h2>
                </div>
                <p>Loading...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="loop-monitor error">
                <div className="loop-monitor-header">
                    <h2>🤖 Autonomous Loops</h2>
                </div>
                <p className="error-message">Error: {error}</p>
            </div>
        );
    }

    const getHealthClass = (health: string) => {
        switch (health) {
            case 'healthy': return 'health-healthy';
            case 'warning': return 'health-warning';
            case 'overdue':
            case 'failed': return 'health-failed';
            case 'never_run': return 'health-never-run';
            default: return '';
        }
    };

    const getLoopDisplayName = (loop: string) => {
        return loop.split('-').map(word =>
            word.charAt(0).toUpperCase() + word.slice(1)
        ).join(' ');
    };

    return (
        <div className="loop-monitor">
            <div className="loop-monitor-header">
                <h2>🤖 Autonomous Loops</h2>
                <button onClick={() => fetchLoopStatus()} className="refresh-button" title="Refresh">
                    ↻
                </button>
            </div>

            <div className="loop-grid">
                {loops.map((loop) => (
                    <div key={loop.loop} className={`loop-card ${getHealthClass(loop.health)}`}>
                        <div className="loop-card-header">
                            <span className="loop-name">{getLoopDisplayName(loop.loop)}</span>
                            <span className="loop-health-icon">{loop.health_icon}</span>
                        </div>

                        <div className="loop-card-body">
                            <div className="loop-stat">
                                <span className="stat-label">Last Run:</span>
                                <span className="stat-value">{loop.last_run_human}</span>
                            </div>

                            <div className="loop-stat">
                                <span className="stat-label">Status:</span>
                                <span className="stat-value">{loop.status}</span>
                            </div>

                            {loop.cards_created > 0 && (
                                <div className="loop-stat highlight">
                                    <span className="stat-label">Cards Created:</span>
                                    <span className="stat-value">{loop.cards_created}</span>
                                </div>
                            )}

                            {loop.duration_seconds !== null && (
                                <div className="loop-stat">
                                    <span className="stat-label">Duration:</span>
                                    <span className="stat-value">{loop.duration_seconds.toFixed(2)}s</span>
                                </div>
                            )}

                            {loop.error && (
                                <div className="loop-error">
                                    <strong>Error:</strong> {loop.error}
                                </div>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
