"""Keep GitHub subprocess collection off the dashboard's request thread."""

import logging
import math
import threading
from time import monotonic

logger = logging.getLogger(__name__)


class GitHubCache:
    """One collector per process; readers never wait for GitHub.

    Keep the last successful snapshot on refresh failures and throttle retries.
    The daemon worker follows the dashboard's existing background-thread model.
    """

    def __init__(self, ttl=300, retry_delay=60, clock=monotonic):
        self._ttl = ttl
        self._retry_delay = retry_delay
        self._clock = clock
        self._lock = threading.Lock()
        self._data = None
        self._expires = 0
        self._next_attempt = 0
        self._refreshing = False
        self._error = None

    def read(self, fetch):
        with self._lock:
            now = self._clock()
            if not self._refreshing and now >= self._next_attempt:
                self._refreshing = True
                self._error = None
                try:
                    threading.Thread(
                        target=self._refresh, args=(fetch,), daemon=True,
                        name="github-refresh",
                    ).start()
                except Exception:
                    logger.exception("Could not start GitHub refresh")
                    self._failed(now)

            return {
                **(self._data or {}),
                "cached": self._data is not None,
                "refreshing": self._refreshing,
                "stale": self._data is not None and now >= self._expires,
                "refresh_error": self._error,
                "retry_after_seconds": (
                    2 if self._refreshing else max(1, math.ceil(self._next_attempt - now))
                ),
            }

    def _failed(self, now):
        self._error = "GitHub refresh failed. Retrying shortly."
        self._next_attempt = now + self._retry_delay
        self._refreshing = False

    def _refresh(self, fetch):
        try:
            data = fetch()
            if not isinstance(data, dict) or data.get("error"):
                raise ValueError("GitHub collector did not return a successful snapshot")
        except Exception:
            logger.exception("GitHub refresh failed")
            with self._lock:
                self._failed(self._clock())
        else:
            with self._lock:
                self._data = data
                self._expires = self._clock() + self._ttl
                self._next_attempt = self._expires
                self._refreshing = False
                self._error = None
