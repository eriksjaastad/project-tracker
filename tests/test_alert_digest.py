"""Tests for scripts/alert_digest.py — the daily portfolio digest email.

What these pin, and why:

- The digest is the *only* thing that tells Erik something broke. Every failure
  mode here is "the email silently stops being useful", so the tests lean on the
  degrade-don't-crash paths rather than the happy path.
- The module is importable with zero side effects (imports + constants only),
  and all I/O sits behind five patchable module-level functions: fetch_alerts,
  fetch_mini_data, fetch_tasks, fetch_scheduled_jobs, send_email.
- Nothing here may touch the network, the Mac Mini, or launchd. Every test that
  reaches a subprocess patches it, so the file passes on ubuntu-latest where
  `launchctl` and `ssh` to the Mini do not exist.
"""

import io
import json
import urllib.error

import pytest

from scripts import alert_digest as ad


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_sleep_no_logfile(monkeypatch, tmp_path):
    """Neutralize the two things that make this file slow or dirty.

    RETRY_BACKOFF_SECONDS is 3 and there are four retry loops of 3 attempts —
    unpatched, this file would take 20+ seconds. And log() appends to
    <repo>/logs/alert_digest.log, which tests have no business writing to.
    """
    monkeypatch.setattr(ad.time, "sleep", lambda _s: None)
    monkeypatch.setattr(ad, "LOG_FILE", tmp_path / "logs" / "alert_digest.log")


class _FakeResp:
    """Minimal stand-in for the urlopen context manager."""

    def __init__(self, payload, code=200):
        self._body = json.dumps(payload).encode("utf-8")
        self._code = code

    def read(self):
        return self._body

    def getcode(self):
        return self._code

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code=500, body=b"quota exceeded"):
    return urllib.error.HTTPError(
        "https://api.resend.com/emails", code, "err", {}, io.BytesIO(body)
    )


def _stub_fetchers(monkeypatch, *, mini=None, tasks=None, jobs=None):
    """Cut every external dependency of main(): no HTTP, no ssh, no launchctl."""
    monkeypatch.setattr(ad, "fetch_mini_data", lambda: mini)
    monkeypatch.setattr(ad, "fetch_tasks", lambda: tasks)
    monkeypatch.setattr(ad, "fetch_scheduled_jobs", lambda: jobs)


# --- 1. RESEND_API_KEY guard ------------------------------------------------
# "Secrets come from Doppler. A missing secret must crash the app, not silently
# stub it." This is the one place the digest is allowed to hard-fail.

class TestApiKeyGuard:

    def test_send_email_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        with pytest.raises(RuntimeError) as exc:
            ad.send_email("subject", "<p>body</p>")
        msg = str(exc.value)
        assert "RESEND_API_KEY" in msg
        assert "doppler run" in msg

    def test_guard_fires_before_any_network_call(self, monkeypatch):
        """No fallback send, no half-attempt: it raises before urlopen."""
        monkeypatch.delenv("RESEND_API_KEY", raising=False)

        def _boom(*a, **kw):  # pragma: no cover - must never run
            raise AssertionError("urlopen must not be reached without a key")

        monkeypatch.setattr(ad.urllib.request, "urlopen", _boom)
        with pytest.raises(RuntimeError):
            ad.send_email("subject", "<p>body</p>")


# --- 2. Retry logic ---------------------------------------------------------
# Four loops of identical shape, MAX_RETRIES = 3. Each is pinned for: recovers
# on attempt 2, gives up after *exactly* MAX_RETRIES attempts.

class TestFetchAlertsRetries:

    def test_succeeds_on_second_attempt(self, monkeypatch):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            if len(calls) == 1:
                raise urllib.error.URLError("connection refused")
            return _FakeResp({"alerts": [{"project_id": "a"}]})

        monkeypatch.setattr(ad.urllib.request, "urlopen", fake_urlopen)
        assert ad.fetch_alerts() == [{"project_id": "a"}]
        assert len(calls) == 2

    def test_gives_up_after_exactly_max_retries(self, monkeypatch):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(ad.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(RuntimeError) as exc:
            ad.fetch_alerts()
        assert len(calls) == ad.MAX_RETRIES == 3
        assert "unreachable" in str(exc.value)

    def test_missing_alerts_key_is_empty_not_crash(self, monkeypatch):
        monkeypatch.setattr(
            ad.urllib.request, "urlopen", lambda req, timeout=None: _FakeResp({})
        )
        assert ad.fetch_alerts() == []


class TestFetchTasksRetries:

    def test_succeeds_on_second_attempt(self, monkeypatch):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            if len(calls) == 1:
                raise urllib.error.URLError("nope")
            return _FakeResp({"tasks": [{"display_id": "1"}]})

        monkeypatch.setattr(ad.urllib.request, "urlopen", fake_urlopen)
        assert ad.fetch_tasks() == [{"display_id": "1"}]
        assert len(calls) == 2

    def test_returns_none_after_exactly_max_retries(self, monkeypatch):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            raise urllib.error.URLError("nope")

        monkeypatch.setattr(ad.urllib.request, "urlopen", fake_urlopen)
        # Unlike fetch_alerts, tasks degrade to None rather than raising —
        # a missing board must not take down the whole digest.
        assert ad.fetch_tasks() is None
        assert len(calls) == ad.MAX_RETRIES

    def test_unexpected_shape_is_retried_then_none(self, monkeypatch):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            return _FakeResp({"tasks": {"not": "a list"}})

        monkeypatch.setattr(ad.urllib.request, "urlopen", fake_urlopen)
        assert ad.fetch_tasks() is None
        assert len(calls) == ad.MAX_RETRIES


class TestFetchMiniRetries:
    """The Mini path shells out over SSH — always patched, never dialed."""

    @pytest.fixture
    def scanner(self, monkeypatch, tmp_path):
        script = tmp_path / "mini_scan.py"
        script.write_text("print('{}')\n")
        monkeypatch.setattr(ad, "MINI_SCAN_SCRIPT", script)
        monkeypatch.setattr(ad, "MINI_ENABLED", True)
        return script

    def test_disabled_short_circuits_without_ssh(self, monkeypatch):
        monkeypatch.setattr(ad, "MINI_ENABLED", False)

        def _boom(*a, **kw):  # pragma: no cover - must never run
            raise AssertionError("ssh must not be spawned when disabled")

        monkeypatch.setattr(ad.subprocess, "run", _boom)
        assert ad.fetch_mini_data() is None

    def test_missing_scanner_short_circuits(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ad, "MINI_ENABLED", True)
        monkeypatch.setattr(ad, "MINI_SCAN_SCRIPT", tmp_path / "absent.py")

        def _boom(*a, **kw):  # pragma: no cover - must never run
            raise AssertionError("ssh must not be spawned without a scanner")

        monkeypatch.setattr(ad.subprocess, "run", _boom)
        assert ad.fetch_mini_data() is None

    def test_succeeds_on_second_attempt(self, monkeypatch, scanner):
        calls = []

        class _Proc:
            def __init__(self, rc, out="", err=""):
                self.returncode, self.stdout, self.stderr = rc, out, err

        def fake_run(cmd, **kw):
            calls.append(cmd)
            if len(calls) == 1:
                return _Proc(255, err="ssh: connect to host ... refused")
            return _Proc(0, out=json.dumps({"projects": [], "scanned_at": "now"}))

        monkeypatch.setattr(ad.subprocess, "run", fake_run)
        data = ad.fetch_mini_data()
        assert data == {"projects": [], "scanned_at": "now"}
        assert len(calls) == 2

    def test_returns_none_after_exactly_max_retries(self, monkeypatch, scanner):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            raise OSError("host down")

        monkeypatch.setattr(ad.subprocess, "run", fake_run)
        assert ad.fetch_mini_data() is None
        assert len(calls) == ad.MAX_RETRIES


class TestSendEmailRetries:

    @pytest.fixture(autouse=True)
    def _key(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")

    def test_succeeds_on_second_attempt(self, monkeypatch):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            if len(calls) == 1:
                raise OSError("transient socket error")
            return _FakeResp({"id": "abc"}, code=200)

        monkeypatch.setattr(ad.urllib.request, "urlopen", fake_urlopen)
        ad.send_email("subject", "<p>hi</p>")
        assert len(calls) == 2

    def test_generic_exception_gives_up_after_max_retries(self, monkeypatch):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            raise OSError("socket dead")

        monkeypatch.setattr(ad.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(RuntimeError) as exc:
            ad.send_email("subject", "<p>hi</p>")
        assert len(calls) == ad.MAX_RETRIES
        assert "socket dead" in str(exc.value)

    def test_http_error_body_is_surfaced(self, monkeypatch):
        """HTTPError is handled separately so Resend's reason reaches the log."""
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            raise _http_error(422, b"domain not verified")

        monkeypatch.setattr(ad.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(RuntimeError) as exc:
            ad.send_email("subject", "<p>hi</p>")
        assert len(calls) == ad.MAX_RETRIES
        msg = str(exc.value)
        assert "HTTP 422" in msg
        assert "domain not verified" in msg

    def test_unexpected_success_code_is_a_failure(self, monkeypatch):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            return _FakeResp({}, code=204)

        monkeypatch.setattr(ad.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(RuntimeError):
            ad.send_email("subject", "<p>hi</p>")
        assert len(calls) == ad.MAX_RETRIES


# --- 3. Ignore filter -------------------------------------------------------

class TestLoadIgnoreList:
    """All three branches fail open to an empty set — a broken ignore file must
    make the digest noisier, never quieter."""

    def test_valid_file(self, monkeypatch, tmp_path):
        f = tmp_path / "ignore.json"
        f.write_text(json.dumps({"macbook": ["proj-a", "proj-b"], "mac-mini": ["m1"]}))
        monkeypatch.setattr(ad, "IGNORE_FILE", f)
        assert ad.load_ignore_list("macbook") == {"proj-a", "proj-b"}
        assert ad.load_ignore_list("mac-mini") == {"m1"}

    def test_unknown_machine_key_is_empty(self, monkeypatch, tmp_path):
        f = tmp_path / "ignore.json"
        f.write_text(json.dumps({"macbook": ["proj-a"]}))
        monkeypatch.setattr(ad, "IGNORE_FILE", f)
        assert ad.load_ignore_list("nonesuch") == set()

    def test_missing_file_fails_open(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ad, "IGNORE_FILE", tmp_path / "absent.json")
        assert ad.load_ignore_list("macbook") == set()

    def test_unparseable_file_fails_open(self, monkeypatch, tmp_path):
        f = tmp_path / "ignore.json"
        f.write_text("{ this is not json")
        monkeypatch.setattr(ad, "IGNORE_FILE", f)
        assert ad.load_ignore_list("macbook") == set()

    def test_wrong_json_shape_fails_open(self, monkeypatch, tmp_path):
        f = tmp_path / "ignore.json"
        f.write_text(json.dumps(["macbook"]))  # list, not dict
        monkeypatch.setattr(ad, "IGNORE_FILE", f)
        assert ad.load_ignore_list("macbook") == set()


class TestIgnoreFilterKeyAsymmetry:
    """The two machines filter on DIFFERENT keys, and that is load-bearing:
    main() matches alerts on ``project_id``; render_mini_section matches Mini
    projects on ``name`` (the Mini scan has no ids, only directory names).
    Anyone "unifying" these will break one machine's ignore list silently.
    """

    def test_macbook_filters_on_project_id_not_name(self, monkeypatch, tmp_path, capsys):
        _stub_fetchers(monkeypatch)
        f = tmp_path / "ignore.json"
        f.write_text(json.dumps({"macbook": ["hidden"], "mac-mini": []}))
        monkeypatch.setattr(ad, "IGNORE_FILE", f)
        monkeypatch.setattr(ad, "fetch_alerts", lambda: [
            {"project_id": "hidden", "project_name": "Shown Name",
             "severity": "critical", "message": "dropped by id"},
            {"project_id": "other", "project_name": "hidden",
             "severity": "critical", "message": "kept despite matching name"},
        ])
        assert ad.main(["--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "dropped by id" not in out
        assert "kept despite matching name" in out

    def test_mini_filters_on_name(self):
        mini = {
            "scanned_at": "2026-09-05T07:00:00Z",
            "projects": [
                {"name": "hidden", "days_since": 1},
                {"name": "visible", "days_since": 1},
            ],
        }
        html = ad.render_mini_section(mini, {"hidden"})
        assert "visible" in html
        assert "hidden" not in html
        assert "Scanned 1 projects" in html

    def test_mini_ignoring_by_id_would_not_work(self):
        """Sanity check on the asymmetry: a project_id-shaped entry misses."""
        mini = {"projects": [{"name": "visible", "days_since": 1}]}
        html = ad.render_mini_section(mini, {"some-project-id"})
        assert "visible" in html


# --- 4. Degraded-mode render ------------------------------------------------

class TestDegradedMode:

    def test_unreachable_dashboard_degrades_instead_of_going_silent(
        self, monkeypatch, tmp_path, capsys
    ):
        _stub_fetchers(monkeypatch)
        monkeypatch.setattr(ad, "IGNORE_FILE", tmp_path / "absent.json")

        def _raise():
            raise RuntimeError("dashboard unreachable after 3 attempts: refused")

        monkeypatch.setattr(ad, "fetch_alerts", _raise)

        sent = []
        monkeypatch.setattr(ad, "send_email", lambda s, h: sent.append((s, h)))

        assert ad.main(["--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "Subject: [Project Alerts] ⚠️ Digest degraded" in out
        assert "Could not read alerts on this machine" in out
        assert "dashboard unreachable after 3 attempts" in out
        # --dry-run must never send.
        assert sent == []

    def test_dry_run_never_sends_on_the_happy_path_either(
        self, monkeypatch, tmp_path, capsys
    ):
        _stub_fetchers(monkeypatch)
        monkeypatch.setattr(ad, "IGNORE_FILE", tmp_path / "absent.json")
        monkeypatch.setattr(ad, "fetch_alerts", lambda: [])
        sent = []
        monkeypatch.setattr(ad, "send_email", lambda s, h: sent.append((s, h)))

        assert ad.main(["--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "Subject: [Project Alerts] ✅ All clear" in out
        assert sent == []

    def test_send_failure_returns_nonzero_without_raising(
        self, monkeypatch, tmp_path
    ):
        _stub_fetchers(monkeypatch)
        monkeypatch.setattr(ad, "IGNORE_FILE", tmp_path / "absent.json")
        monkeypatch.setattr(ad, "fetch_alerts", lambda: [])

        def _fail(subject, html):
            raise RuntimeError("resend down")

        monkeypatch.setattr(ad, "send_email", _fail)
        assert ad.main([]) == 1

    def test_successful_send_returns_zero(self, monkeypatch, tmp_path):
        _stub_fetchers(monkeypatch)
        monkeypatch.setattr(ad, "IGNORE_FILE", tmp_path / "absent.json")
        monkeypatch.setattr(ad, "fetch_alerts", lambda: [
            {"project_id": "p", "project_name": "P", "severity": "warning",
             "message": "m", "details": "d"},
        ])
        sent = []
        monkeypatch.setattr(ad, "send_email", lambda s, h: sent.append((s, h)))
        assert ad.main([]) == 0
        assert len(sent) == 1
        assert sent[0][0] == "[Project Alerts] 🟡 1 warning"


class TestSubjectLine:

    def test_all_clear(self):
        assert ad.build_subject([]) == "[Project Alerts] ✅ All clear"

    def test_counts_by_severity(self):
        alerts = [
            {"severity": "critical"}, {"severity": "warning"},
            {"severity": "warning"}, {"severity": "info"},
        ]
        assert ad.build_subject(alerts) == (
            "[Project Alerts] 🔴 1 critical, 🟡 2 warnings, 🔵 1 info"
        )


# --- 5. Escaping regressions (#6439) ----------------------------------------
# Every value below arrives from outside the digest: alert_detector passes
# through scanned project text, project names come from disk/DB, and the Mini
# error string is whatever came back over SSH.

XSS = '<script>alert("pwned")</script>'


def _assert_escaped(html: str) -> None:
    assert "<script>" not in html
    assert "</script>" not in html
    assert "&lt;script&gt;" in html


class TestHtmlEscaping:

    def test_esc_handles_the_three_text_node_chars(self):
        assert ad._esc("a & b < c > d") == "a &amp; b &lt; c &gt; d"
        assert ad._esc(42) == "42"

    def test_alert_row_project_name_is_escaped(self):
        html = ad._render_alert_rows(
            [{"project_name": XSS, "severity": "critical", "message": "m", "details": "d"}]
        )
        _assert_escaped(html)

    def test_alert_row_message_is_escaped(self):
        html = ad._render_alert_rows(
            [{"project_name": "p", "severity": "critical", "message": XSS, "details": "d"}]
        )
        _assert_escaped(html)

    def test_alert_row_details_is_escaped(self):
        html = ad._render_alert_rows(
            [{"project_name": "p", "severity": "critical", "message": "m", "details": XSS}]
        )
        _assert_escaped(html)

    def test_mini_error_string_is_escaped(self):
        """The most attacker-adjacent value: an error returned over SSH."""
        html = ad.render_mini_section({"error": XSS}, set())
        _assert_escaped(html)

    def test_mini_scanned_at_is_escaped(self):
        html = ad.render_mini_section(
            {"scanned_at": XSS, "projects": [{"name": "p", "days_since": 1}]}, set()
        )
        _assert_escaped(html)

    def test_mini_active_project_name_is_escaped(self):
        html = ad.render_mini_section(
            {"scanned_at": "now", "projects": [{"name": XSS, "days_since": 1}]}, set()
        )
        _assert_escaped(html)

    def test_mini_stale_project_name_is_escaped(self):
        html = ad.render_mini_section(
            {"scanned_at": "now",
             "projects": [{"name": XSS, "days_since": ad.STALE_DAYS + 5}]},
            set(),
        )
        _assert_escaped(html)
        assert "Stale (60+ days)" in html

    def test_full_email_render_is_escaped_end_to_end(self):
        html = ad.render_html(
            macbook_alerts=[{"project_name": XSS, "severity": "critical",
                             "message": XSS, "details": XSS}],
            mini_data={"scanned_at": XSS,
                       "projects": [{"name": XSS, "days_since": 2}],
                       "jobs": [{"label": "com.pt." + XSS, "pid": None,
                                 "last_exit": 1}]},
            mini_ignore=set(),
            tasks=[{"display_id": "1", "title": XSS, "project_id": XSS,
                    "status": "In Progress", "updated_at": "2026-09-01"}],
            jobs=[{"label": "com.pt." + XSS, "pid": None, "last_exit": 1}],
            degraded_reason=None,
            sent_at="Friday, September 05 2026 · 7:00 AM",
        )
        _assert_escaped(html)


# --- Rendering odds and ends ------------------------------------------------

class TestCardsAndJobsRendering:

    def test_cards_section_notice_when_board_unreadable(self):
        html = ad.render_cards_section(None)
        assert "Could not read the board this run" in html

    def test_backlog_is_grouped_by_project_not_listed(self):
        tasks = [
            {"display_id": str(i), "title": f"card {i}", "project_id": "alpha",
             "status": "Backlog"} for i in range(5)
        ]
        html = ad.render_cards_section(tasks)
        assert "🗄️ Backlog (5)" in html
        assert "card 0" not in html
        assert "alpha" in html

    def test_jobs_notice_when_launchctl_unavailable(self):
        """None (e.g. Linux, no launchctl) renders a notice, not a crash."""
        html = ad.render_jobs_section(None, None)
        assert html.count("no job data this run") == 2

    def test_failed_job_is_flagged_and_sorted_first(self):
        html = ad._render_job_group([
            {"label": "com.pt.aaa_ok", "pid": None, "last_exit": 0},
            {"label": "com.pt.zzz_bad", "pid": None, "last_exit": 3},
        ])
        assert "FAILED (exit 3)" in html
        assert html.index("zzz_bad") < html.index("aaa_ok")


class TestFetchScheduledJobs:
    """launchctl does not exist on Linux CI, so the subprocess is always patched."""

    class _Proc:
        def __init__(self, rc, out="", err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def test_parses_and_filters_to_our_labels(self, monkeypatch):
        out = (
            "PID\tStatus\tLabel\n"
            "-\t0\tcom.apple.something\n"
            "1234\t0\tcom.eriksjaastad.digest\n"
            "-\t1\tcom.pt.dashboard\n"
            "-\t-\tcom.pt.neverrun\n"
        )
        monkeypatch.setattr(
            ad.subprocess, "run", lambda cmd, **kw: self._Proc(0, out=out)
        )
        jobs = ad.fetch_scheduled_jobs()
        assert [j["label"] for j in jobs] == [
            "com.eriksjaastad.digest", "com.pt.dashboard", "com.pt.neverrun"
        ]
        assert jobs[0]["pid"] == "1234"
        assert jobs[1]["last_exit"] == 1
        assert jobs[2]["pid"] is None and jobs[2]["last_exit"] is None

    def test_malformed_status_column_does_not_crash(self, monkeypatch):
        out = "PID\tStatus\tLabel\n-\tWAT\tcom.pt.weird\n"
        monkeypatch.setattr(
            ad.subprocess, "run", lambda cmd, **kw: self._Proc(0, out=out)
        )
        jobs = ad.fetch_scheduled_jobs()
        assert jobs == [{"label": "com.pt.weird", "pid": None, "last_exit": None}]

    def test_nonzero_exit_degrades_to_none(self, monkeypatch):
        monkeypatch.setattr(
            ad.subprocess, "run", lambda cmd, **kw: self._Proc(1, err="boom")
        )
        assert ad.fetch_scheduled_jobs() is None

    def test_missing_launchctl_degrades_to_none(self, monkeypatch):
        def _missing(cmd, **kw):
            raise FileNotFoundError("launchctl")

        monkeypatch.setattr(ad.subprocess, "run", _missing)
        assert ad.fetch_scheduled_jobs() is None
