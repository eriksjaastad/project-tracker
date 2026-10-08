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
from datetime import timedelta
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


_REAL_FETCH_PAUSED_LOOPS = ad.fetch_paused_review_loops


@pytest.fixture(autouse=True)
def _no_live_review_loop_scan(monkeypatch):
    """Keep every test off the live ~/.claude launcher and its history.

    The paused-loop scan reads machine state; on a host without the launcher
    (CI) it reports a scan failure in every subject. Tests that exercise the
    scan reinstate the real function explicitly.
    """
    monkeypatch.setattr(
        ad, "fetch_paused_review_loops",
        lambda now=None: {"loops": [], "errors": [], "fatal": None, "history_dir": ""},
    )


_REAL_FETCH_CALENDAR = ad.fetch_calendar_events


@pytest.fixture(autouse=True)
def _no_live_calendar(monkeypatch):
    """Keep every test off the live dashboard's calendar (no events by default)."""
    monkeypatch.setattr(ad, "fetch_calendar_events", lambda: [])


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

    # --- #7755: documented non-failure exit codes render as ATTENTION, not FAILED ---

    SEO_LABEL = "com.eriksjaastad.hypocrisynow-seo"

    def test_documented_attention_exit_renders_attention_not_failed(self):
        """exit 2 for the seo job is a documented non-failure state (README.md)."""
        html = ad._render_job_group([
            {"label": self.SEO_LABEL, "pid": None, "last_exit": 2},
        ])
        assert "FAILED" not in html
        assert "ATTENTION (exit 2)" in html
        # The report path is surfaced so the email is actionable, not just quiet.
        assert "seo-monitor/report.md" in html

    def test_same_job_undocumented_exit_is_still_failed(self):
        """exit 1 for the SAME job is a real collector/monitor failure per README.md."""
        html = ad._render_job_group([
            {"label": self.SEO_LABEL, "pid": None, "last_exit": 1},
        ])
        assert "FAILED (exit 1)" in html
        assert "ATTENTION" not in html

    def test_unlisted_job_same_exit_code_is_failed(self):
        """exit 2 means nothing special for a job with no entry in the table —
        never silently downgrade an undocumented code."""
        html = ad._render_job_group([
            {"label": "com.eriksjaastad.some-other-job", "pid": None, "last_exit": 2},
        ])
        assert "FAILED (exit 2)" in html
        assert "ATTENTION" not in html

    def test_attention_sorts_between_failed_and_ok(self):
        html = ad._render_job_group([
            {"label": "com.pt.aaa_ok", "pid": None, "last_exit": 0},
            {"label": self.SEO_LABEL, "pid": None, "last_exit": 2},
            {"label": "com.pt.zzz_bad", "pid": None, "last_exit": 3},
        ])
        assert html.index("zzz_bad") < html.index("hypocrisynow-seo") < html.index("aaa_ok")

    def test_attention_job_does_not_change_subject_or_counts(self):
        """Scheduled-job state is rendered in its own section and must never
        leak into the dashboard-alert-derived subject/summary counts — an
        ATTENTION job is not a dashboard alert and must not be counted as one."""
        counts_before = ad._summary_counts([])
        subject = ad.build_subject([])
        html = ad.render_jobs_section(
            [{"label": self.SEO_LABEL, "pid": None, "last_exit": 2}], None
        )
        assert "ATTENTION" in html
        # Subject/counts are built from dashboard alerts only; an empty alerts
        # list stays "All clear" regardless of job state.
        assert subject == "[Project Alerts] ✅ All clear"
        assert counts_before == {"critical": 0, "warning": 0, "info": 0}


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


# --- escaping helpers (#6881) ----------------------------------------------


def test_esc_handles_text_node_characters():
    assert ad._esc('<script>&</script>') == (
        "&lt;script&gt;&amp;&lt;/script&gt;"
    )


def test_esc_attr_also_neutralises_quotes():
    """A quote inside an attribute value closes it early; _esc alone doesn't
    stop that, which is the whole reason _esc_attr exists."""
    hostile = '" onmouseover=alert(1) x="'
    assert '"' in ad._esc(hostile), "_esc is text-node-only by design"
    escaped = ad._esc_attr(hostile)
    assert '"' not in escaped
    assert "&quot;" in escaped


def test_esc_attr_escapes_single_quotes_too():
    assert "'" not in ad._esc_attr("it's")
    assert "&#x27;" in ad._esc_attr("it's")


# --- Paused review loops (#7755) --------------------------------------------

_FAKE_LAUNCHER = '''
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

STATE = Path(__STATE__)


class HistoryError(RuntimeError):
    pass


def history_path(slug, branch):
    return STATE / "codex_history" / "x.jsonl"


def _validate_event(event, path, lineno):
    if not isinstance(event, dict) or "type" not in event or "ts" not in event:
        raise HistoryError(f"{path} line {lineno} malformed")


@dataclass
class LoopState:
    rounds: list = field(default_factory=list)
    tripped: bool = False
    tripped_at: Optional[str] = None
    trip_reason: Optional[str] = None
    notified: bool = False
    fail_count: int = 0
    should_trip: bool = False
    pending_trip_reason: Optional[str] = None


def loop_state(events, now):
    rounds = [e for e in events if e["type"] == "round"]
    fails = sum(1 for r in rounds if r["outcome"] == "FAIL")
    trips = [e for e in events if e["type"] == "trip"]
    return LoopState(
        rounds=rounds, tripped=bool(trips),
        tripped_at=trips[0]["ts"] if trips else None,
        trip_reason=trips[0]["reason"] if trips else None,
        notified=any(e["type"] == "notify" and e.get("ok") for e in events),
        fail_count=fails, should_trip=fails >= 3 and not trips,
        pending_trip_reason=f"{fails} FAIL verdicts" if fails >= 3 and not trips else None,
    )
'''


def _ev(ts_min, etype, **fields):
    return {"ts": f"2026-10-01T10:{ts_min:02d}:00+00:00", "type": etype, **fields}


def _install_fake_launcher(monkeypatch, tmp_path, state):
    launcher = tmp_path / "launcher.py"
    launcher.write_text(_FAKE_LAUNCHER.replace("__STATE__", repr(str(state))))
    monkeypatch.setattr(ad, "CODEX_LAUNCHER", launcher)


class TestPausedReviewLoops:

    @pytest.fixture(autouse=True)
    def _real_scan(self, monkeypatch):
        monkeypatch.setattr(ad, "fetch_paused_review_loops", _REAL_FETCH_PAUSED_LOOPS)

    @pytest.fixture
    def fake(self, monkeypatch, tmp_path):
        state = tmp_path / "state"
        _install_fake_launcher(monkeypatch, tmp_path, state)
        hist = state / "codex_history"
        hist.mkdir(parents=True)

        def write(name, events):
            (hist / f"{name}__0123456789ab.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in events)
            )
        return hist, write

    def test_tripped_unnotified_loop_is_listed_and_flagged(self, fake):
        _hist, write = fake
        write("o__repo__feat__1-x", [
            _ev(1, "round", outcome="FAIL", head_sha="a" * 40),
            _ev(2, "trip", reason="3 FAIL verdicts"),
            _ev(3, "notify", ok=False, error="pt message down"),
        ])
        write("o__repo__feat__2-ok", [_ev(1, "round", outcome="PASS", head_sha="b" * 40)])
        res = ad.fetch_paused_review_loops()
        assert res["fatal"] is None and res["errors"] == []
        assert [lp["loop"] for lp in res["loops"]] == ["o__repo__feat__1-x"]
        lp = res["loops"][0]
        assert lp["notified"] is False and lp["notify_error"] == "pt message down"
        html = ad.render_review_loops_section(res)
        assert "architect NOT notified (pt message down)" in html
        assert "o__repo__feat__1-x" in html and "aaaaaaaaaaaa" in html
        assert ad.build_subject([], res) == "[Project Alerts] ⏸️ 1 paused review loop"

    def test_threshold_met_without_trip_event_counts_as_paused(self, fake):
        _hist, write = fake
        write("o__r__b", [_ev(i, "round", outcome="FAIL") for i in range(3)])
        res = ad.fetch_paused_review_loops()
        assert res["loops"][0]["trip_recorded"] is False
        assert "trip NOT recorded" in ad.render_review_loops_section(res)

    def test_notified_loop_has_no_flag(self, fake):
        _hist, write = fake
        write("o__r__b", [_ev(1, "trip", reason="r"), _ev(2, "notify", ok=True)])
        html = ad.render_review_loops_section(ad.fetch_paused_review_loops())
        assert "⏸️" in html and "NOT" not in html

    def test_malformed_log_is_loud_and_other_logs_still_scanned(self, fake):
        hist, write = fake
        (hist / "o__r__bad__0123456789ab.jsonl").write_text("{not json\n")
        write("o__r__good", [_ev(1, "trip", reason="r")])
        res = ad.fetch_paused_review_loops()
        assert [e["loop"] for e in res["errors"]] == ["o__r__bad"]
        assert [lp["loop"] for lp in res["loops"]] == ["o__r__good"]
        assert "Unreadable tripwire log: o__r__bad" in ad.render_review_loops_section(res)
        assert "review-loop scan failed" in ad.build_subject([], res)

    def test_missing_history_dir_is_fatal_not_empty(self, monkeypatch, tmp_path):
        _install_fake_launcher(monkeypatch, tmp_path, tmp_path / "absent")
        res = ad.fetch_paused_review_loops()
        assert res["fatal"] and "history directory" in res["fatal"]
        html = ad.render_review_loops_section(res)
        assert "Could not check for paused review loops" in html
        assert "No paused review loops" not in html
        assert "review-loop scan failed" in ad.build_subject([], res)

    def test_unreadable_history_dir_is_fatal_not_empty(self, monkeypatch, tmp_path):
        """is_dir() is False on a permission-denied parent; must not read as empty."""
        state = tmp_path / "state"
        (state / "codex_history").mkdir(parents=True)
        _install_fake_launcher(monkeypatch, tmp_path, state)
        state.chmod(0)
        try:
            res = ad.fetch_paused_review_loops()
        finally:
            state.chmod(0o755)
        assert res["fatal"] and "Permission denied" in res["fatal"]

    def test_launcher_exiting_on_import_is_fatal_not_a_crash(self, monkeypatch, tmp_path):
        """The real launcher raises SystemExit(3) on a bad CODEX_REVIEW_* value."""
        launcher = tmp_path / "launcher.py"
        launcher.write_text("import sys\nsys.exit(3)\n")
        monkeypatch.setattr(ad, "CODEX_LAUNCHER", launcher)
        res = ad.fetch_paused_review_loops()
        assert res["fatal"] and "review launcher" in res["fatal"]

    def test_launcher_exiting_mid_scan_is_a_per_log_error(self, fake, monkeypatch):
        _hist, write = fake
        write("o__r__b", [_ev(1, "trip", reason="r")])
        real_load = ad._load_codex_launcher

        def load():
            mod = real_load()
            mod.loop_state = lambda events, now: (_ for _ in ()).throw(SystemExit(3))
            return mod
        monkeypatch.setattr(ad, "_load_codex_launcher", load)
        res = ad.fetch_paused_review_loops()
        assert [e["loop"] for e in res["errors"]] == ["o__r__b"]

    def test_unlistable_history_dir_is_fatal_not_empty(self, fake):
        """The directory exists and stats fine but cannot be listed."""
        hist, write = fake
        write("o__r__stuck", [_ev(1, "trip", reason="r")])
        hist.chmod(0o300)  # write+search, no read: listing fails
        try:
            res = ad.fetch_paused_review_loops()
        finally:
            hist.chmod(0o755)
        assert res["fatal"] and "Permission denied" in res["fatal"]
        assert "review-loop scan failed" in ad.build_subject([], res)

    def test_missing_launcher_is_fatal_not_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ad, "CODEX_LAUNCHER", tmp_path / "nope.py")
        res = ad.fetch_paused_review_loops()
        assert res["fatal"] and "review launcher" in res["fatal"]
        assert res["loops"] == []

    def test_quiet_when_nothing_paused(self, fake):
        _hist, write = fake
        write("o__r__b", [_ev(1, "round", outcome="PASS")])
        res = ad.fetch_paused_review_loops()
        assert ad.render_review_loops_section(res).count("No paused review loops") == 1
        assert ad.build_subject([], res) == "[Project Alerts] ✅ All clear"

    def test_section_is_rendered_into_the_email(self, fake):
        res = ad.fetch_paused_review_loops()
        html = ad.render_html([], None, set(), None, None, None, "now", res)
        assert "Paused Review Loops" in html

    def test_main_puts_paused_loops_in_the_dry_run_email(self, fake, monkeypatch, capsys):
        _hist, write = fake
        write("o__r__stuck", [_ev(1, "trip", reason="7 FAIL verdicts")])
        monkeypatch.setattr(ad, "fetch_alerts", lambda: [])
        monkeypatch.setattr(ad, "fetch_mini_data", lambda: None)
        monkeypatch.setattr(ad, "fetch_tasks", lambda: [])
        monkeypatch.setattr(ad, "fetch_scheduled_jobs", lambda: [])
        assert ad.main(["--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "Subject: [Project Alerts] ⏸️ 1 paused review loop" in out
        assert "o__r__stuck" in out and "7 FAIL verdicts" in out

    def test_degraded_subject_still_names_paused_loops(self, fake, monkeypatch, capsys):
        _hist, write = fake
        write("o__r__stuck", [_ev(1, "trip", reason="r")])

        def boom():
            raise RuntimeError("dashboard down")
        monkeypatch.setattr(ad, "fetch_alerts", boom)
        monkeypatch.setattr(ad, "fetch_mini_data", lambda: None)
        monkeypatch.setattr(ad, "fetch_tasks", lambda: [])
        monkeypatch.setattr(ad, "fetch_scheduled_jobs", lambda: [])
        assert ad.main(["--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "Subject: [Project Alerts] ⚠️ Digest degraded, ⏸️ 1 paused review loop" in out


class TestLoadCodexLauncher:
    def test_launcher_can_import_its_sibling_modules(self, monkeypatch, tmp_path):
        # The real launcher does `import user_presence` from its own directory (#7915).
        sibling = "_digest_test_sibling_module"
        (tmp_path / f"{sibling}.py").write_text("VALUE = 7\n")
        launcher_path = tmp_path / "launcher.py"
        launcher_path.write_text(f"import {sibling}\nFAIL_LIMIT = {sibling}.VALUE\n")
        monkeypatch.setattr(ad, "CODEX_LAUNCHER", launcher_path)
        monkeypatch.delitem(ad.sys.modules, sibling, raising=False)
        path_before = list(ad.sys.path)
        try:
            assert ad._load_codex_launcher().FAIL_LIMIT == 7
        finally:
            ad.sys.modules.pop(sibling, None)
        assert ad.sys.path == path_before

    def test_sys_path_is_restored_when_the_launcher_fails(self, monkeypatch, tmp_path):
        launcher_path = tmp_path / "launcher.py"
        launcher_path.write_text("raise RuntimeError('boom')\n")
        monkeypatch.setattr(ad, "CODEX_LAUNCHER", launcher_path)
        path_before = list(ad.sys.path)
        with pytest.raises(RuntimeError, match="boom"):
            ad._load_codex_launcher()
        assert ad.sys.path == path_before


_REAL_LAUNCHER = ad.Path.home() / ".claude" / "scripts" / "codex_pr_review.py"


@pytest.mark.skipif(not _REAL_LAUNCHER.is_file(), reason="claude-user-config launcher not installed")
class TestPausedReviewLoopsAgainstRealLauncher:
    """Contract check: the digest reads logs written by the real launcher."""

    def test_bad_launcher_setting_does_not_stop_the_digest(self, monkeypatch, capsys):
        monkeypatch.setattr(ad, "fetch_paused_review_loops", _REAL_FETCH_PAUSED_LOOPS)
        monkeypatch.setattr(ad, "CODEX_LAUNCHER", _REAL_LAUNCHER)
        monkeypatch.setenv("CODEX_REVIEW_FAIL_LIMIT", "bad")
        monkeypatch.setattr(ad, "fetch_alerts", lambda: [])
        monkeypatch.setattr(ad, "fetch_mini_data", lambda: None)
        monkeypatch.setattr(ad, "fetch_tasks", lambda: [])
        monkeypatch.setattr(ad, "fetch_scheduled_jobs", lambda: [])
        assert ad.main(["--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "review-loop scan failed" in out
        assert "Could not check for paused review loops" in out

    def test_real_trip_is_reported(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ad, "fetch_paused_review_loops", _REAL_FETCH_PAUSED_LOOPS)
        monkeypatch.setenv("PR_REVIEW_STATE_DIR", str(tmp_path))
        monkeypatch.setattr(ad, "CODEX_LAUNCHER", _REAL_LAUNCHER)
        launcher = ad._load_codex_launcher()
        for _ in range(launcher.FAIL_LIMIT):
            launcher.append_event("o__r", "feat/x", "round",
                                  {"outcome": "FAIL", "head_sha": "c" * 40, "findings_count": 1})
        launcher.append_event("o__r", "feat/clean", "round", {"outcome": "PASS", "head_sha": "d" * 40})
        res = ad.fetch_paused_review_loops()
        assert res["fatal"] is None and res["errors"] == []
        assert [lp["loop"] for lp in res["loops"]] == ["o__r__feat__x"]
        assert res["loops"][0]["trip_recorded"] is False

        launcher.append_event("o__r", "feat/x", "trip", {"reason": "limit"})
        lp = ad.fetch_paused_review_loops()["loops"][0]
        assert lp["trip_recorded"] is True and lp["notified"] is False

        launcher.append_event("o__r", "feat/x", "notify", {"ok": True, "error": None, "channel": "pt"})
        assert ad.fetch_paused_review_loops()["loops"][0]["notified"] is True

        launcher.append_event("o__r", "feat/x", "clear", {"reason": "Erik cleared"})
        assert ad.fetch_paused_review_loops()["loops"] == []



# --- Deadlines (#8137) -------------------------------------------------------
# The calendar's only route to Erik: due-soon and recently missed events.

def _event(id_, event_date, title="Thing due", status="active", **extra):
    return {"id": id_, "title": title, "event_date": event_date, "status": status, **extra}


class TestDeadlines:
    TODAY = ad.date(2026, 10, 8)

    def test_window_bounds_status_and_order(self):
        events = [
            _event(1, "2026-10-22", "in 14 days"),         # edge: shown
            _event(2, "2026-10-23", "in 15 days"),         # outside
            _event(3, "2026-09-08", "missed 30 days ago"), # edge: shown
            _event(4, "2026-09-07", "missed 31 days ago"), # stale: hidden
            _event(5, "2026-10-15", "done already", status="done"),
            _event(6, "2026-10-08", "today"),
            _event(7, "2026-10-15T00:00:00", "tax return"),
        ]
        got = ad.upcoming_deadlines(events, self.TODAY)
        assert [(e["id"], e["days"]) for e in got] == [(3, -30), (6, 0), (7, 7), (1, 14)]

    def test_unreadable_date_is_logged_and_skipped(self, monkeypatch):
        lines = []
        monkeypatch.setattr(ad, "log", lines.append)
        assert ad.upcoming_deadlines([_event(9, "not-a-date")], self.TODAY) == []
        assert any("unreadable date" in line for line in lines)

    def test_section_is_absent_on_empty_days(self):
        assert ad.render_deadlines_section([]) == ""
        html = ad.render_html([], None, set(), [], [], None, "now", None, [])
        assert "Deadlines" not in html

    def test_section_lists_due_and_missed_with_escaping(self):
        rows = ad.upcoming_deadlines(
            [_event(1, "2026-10-15", "<b>Extended federal return</b>", project_id="tax-organizer"),
             _event(2, "2026-09-15", "Q3 estimated tax")],
            self.TODAY,
        )
        html = ad.render_deadlines_section(rows)
        assert "in 7 days" in html and "missed 23 days ago" in html
        assert "&lt;b&gt;Extended federal return&lt;/b&gt;" in html and "<b>Extended" not in html
        assert "tax-organizer" in html
        assert html.index("missed 23 days ago") < html.index("in 7 days")

    def test_unreadable_calendar_is_shown_not_hidden(self):
        assert "Could not read the calendar" in ad.render_deadlines_section(None)
        assert "⚠️ calendar unreadable" in ad.build_subject([], None, None)

    def test_subject_names_deadlines_within_a_week_only(self):
        week = ad.upcoming_deadlines([_event(1, "2026-10-15")], self.TODAY)
        later = ad.upcoming_deadlines([_event(2, "2026-10-20")], self.TODAY)
        assert ad.build_subject([], None, week) == "[Project Alerts] 📅 1 deadline due or missed"
        assert ad.build_subject([], None, later) == "[Project Alerts] ✅ All clear"
        assert ad.build_subject([], None) == "[Project Alerts] ✅ All clear"

    def test_main_dry_run_shows_the_tax_deadline(self, monkeypatch, capsys):
        today = ad.date.today()
        due = (today + timedelta(days=6)).isoformat()
        monkeypatch.setattr(ad, "fetch_calendar_events", lambda: [
            _event(9, due, "Extended federal tax return due (2025)", project_id="tax-organizer"),
        ])
        monkeypatch.setattr(ad, "fetch_alerts", lambda: [])
        _stub_fetchers(monkeypatch, tasks=[], jobs=[])
        assert ad.main(["--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "📅 1 deadline due or missed" in out.splitlines()[0]
        assert "📅 Deadlines" in out and "Extended federal tax return due (2025)" in out
        assert "in 6 days" in out

    def test_main_with_calendar_down_says_so(self, monkeypatch, capsys):
        monkeypatch.setattr(ad, "fetch_calendar_events", lambda: None)
        monkeypatch.setattr(ad, "fetch_alerts", lambda: [])
        _stub_fetchers(monkeypatch, tasks=[], jobs=[])
        assert ad.main(["--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "calendar unreadable" in out.splitlines()[0]
        assert "Could not read the calendar" in out

    def test_fetch_reads_events_and_fails_soft(self, monkeypatch):
        monkeypatch.setattr(ad, "fetch_calendar_events", _REAL_FETCH_CALENDAR)
        monkeypatch.setattr(ad.urllib.request, "urlopen",
                            lambda req, timeout=10: _FakeResp({"events": [_event(1, "2026-10-15")], "total": 1}))
        assert [e["id"] for e in ad.fetch_calendar_events()] == [1]
        def down(req, timeout=10):
            raise ad.urllib.error.URLError("refused")
        monkeypatch.setattr(ad.urllib.request, "urlopen", down)
        assert ad.fetch_calendar_events() is None
