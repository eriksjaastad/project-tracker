"""Tests for card_factory_grok.py's OpenRouter routing (#7699).

scripts/card_factory_grok.py is a standalone `uv run --script` tool with its
own PEP 723 dependencies (openai, api-trust-tracker) that are NOT installed
in the shared project-tracker .venv used by the test suite. These tests stub
minimal `openai` / `api_trust_tracker` modules into sys.modules so the file
imports cleanly, then monkeypatch `card_factory_grok.OpenAI` and
`card_factory_grok.track` directly to assert on what the real call sites did
-- without making a network call.

What's asserted:
  - the OpenAI client is built with base_url="https://openrouter.ai/api/v1"
    and api_key read from OPENROUTER_API_KEY (never XAI_API_KEY).
  - the chat completion is requested with the OpenRouter-catalog model id
    "x-ai/grok-build-0.1" (provider-prefixed, not the bare xAI id).
  - cost tracking is attributed to provider "openrouter".
  - a missing OPENROUTER_API_KEY crashes with a clear, specific error and
    does not silently fall back to XAI_API_KEY even if that is set.
"""

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR.parent))  # repo root, for `scripts.config`
sys.path.insert(0, str(SCRIPTS_DIR))


def _install_fake_optional_deps():
    """Install minimal stand-ins for openai/api_trust_tracker in sys.modules.

    Only installed if the real packages are not already importable, so this
    plays nicely in an environment that does happen to have them.
    """
    if "openai" not in sys.modules:
        try:
            import openai  # noqa: F401
        except ImportError:
            fake_openai = types.ModuleType("openai")

            class _PlaceholderOpenAI:  # replaced per-test via monkeypatch
                def __init__(self, **kwargs):
                    raise AssertionError(
                        "real openai.OpenAI should never be constructed in tests; "
                        "monkeypatch card_factory_grok.OpenAI instead"
                    )

            fake_openai.OpenAI = _PlaceholderOpenAI
            sys.modules["openai"] = fake_openai

    if "api_trust_tracker" not in sys.modules:
        try:
            import api_trust_tracker  # noqa: F401
        except ImportError:
            fake_tracker = types.ModuleType("api_trust_tracker")

            def _placeholder_track(resp, provider, **kwargs):  # replaced per-test
                raise AssertionError(
                    "real api_trust_tracker.track should never run in tests; "
                    "monkeypatch card_factory_grok.track instead"
                )

            fake_tracker.track = _placeholder_track
            sys.modules["api_trust_tracker"] = fake_tracker


_install_fake_optional_deps()

import card_factory_grok as grok  # noqa: E402


# ── Fakes for the OpenAI-compatible client ────────────────────────────────


class FakeUsage:
    def __init__(self, prompt_tokens=10, completion_tokens=5, cost=None):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cost = cost


class FakeMessage:
    def __init__(self, content="done scanning.", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=False):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        return d


class FakeResponse:
    def __init__(self, content="done scanning.", usage=None, tool_calls=None):
        self.choices = [SimpleNamespace(message=FakeMessage(content=content, tool_calls=tool_calls))]
        self.usage = usage if usage is not None else FakeUsage()


class FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("test queued fewer fake responses than iterations consumed")
        return self._responses.pop(0)


def make_fake_openai_factory(responses, init_calls):
    """Return a callable usable as a drop-in for the OpenAI(...) constructor."""

    def factory(**kwargs):
        init_calls.append(kwargs)
        completions = FakeCompletions(responses)
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        client._completions = completions  # test convenience handle
        return client

    return factory


@pytest.fixture
def git_project(tmp_path, monkeypatch):
    """A fake project directory with a .git marker, pointed at by PROJECTS_ROOT."""
    project_root = tmp_path / "widget-project"
    (project_root / ".git").mkdir(parents=True)
    monkeypatch.setattr(grok, "PROJECTS_ROOT", tmp_path)
    return "widget-project"


@pytest.fixture
def track_calls(monkeypatch):
    calls = []

    def fake_track(resp, provider, **kwargs):
        calls.append({"provider": provider, **kwargs})
        return resp

    monkeypatch.setattr(grok, "track", fake_track)
    return calls


# ── Tests ──────────────────────────────────────────────────────────────────


def test_client_is_built_against_openrouter(git_project, track_calls, monkeypatch):
    """The OpenAI client must point at OpenRouter's base_url with OPENROUTER_API_KEY."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key-123")
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    init_calls = []
    responses = [FakeResponse()]
    monkeypatch.setattr(grok, "OpenAI", make_fake_openai_factory(responses, init_calls))

    rc = grok.run(git_project, commit=False)

    assert rc == 0
    assert init_calls == [{"api_key": "or-test-key-123", "base_url": "https://openrouter.ai/api/v1"}]


def test_chat_completion_call_kwargs_carry_the_model_id(git_project, track_calls, monkeypatch):
    """OpenRouter requires the provider-prefixed id, not the bare xAI model name."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key-123")

    init_calls = []
    responses = [FakeResponse()]
    captured_client = {}

    def factory(**kwargs):
        init_calls.append(kwargs)
        completions = FakeCompletions(responses)
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        captured_client["client"] = client
        return client

    monkeypatch.setattr(grok, "OpenAI", factory)

    grok.run(git_project, commit=False)

    create_calls = captured_client["client"].chat.completions.calls
    assert len(create_calls) == 1
    assert create_calls[0]["model"] == "x-ai/grok-build-0.1"


def test_cost_tracking_attributed_to_openrouter(git_project, track_calls, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key-123")

    init_calls = []
    responses = [FakeResponse(usage=FakeUsage(prompt_tokens=100, completion_tokens=40, cost=0.00018))]
    monkeypatch.setattr(grok, "OpenAI", make_fake_openai_factory(responses, init_calls))

    grok.run(git_project, commit=False)

    assert len(track_calls) == 1
    assert track_calls[0]["provider"] == "openrouter"
    assert track_calls[0]["project"] == "project-tracker"
    assert track_calls[0]["caller"] == "card-factory-grok"


def test_reported_cost_is_used_over_the_fallback_estimate(git_project, track_calls, monkeypatch, capsys):
    """When OpenRouter reports usage.cost, the printed summary should use it,
    not the hardcoded PRICE_IN_PER_1M/PRICE_OUT_PER_1M estimate."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key-123")

    init_calls = []
    # Deliberately mismatched from the fallback formula so the test would
    # fail if the fallback path were used by mistake.
    reported_cost = 0.0042
    responses = [FakeResponse(usage=FakeUsage(prompt_tokens=100, completion_tokens=40, cost=reported_cost))]
    monkeypatch.setattr(grok, "OpenAI", make_fake_openai_factory(responses, init_calls))

    grok.run(git_project, commit=False)

    out = capsys.readouterr().out
    assert f"est_cost=${reported_cost:.4f}" in out


def test_fallback_estimate_used_when_cost_is_absent(git_project, track_calls, monkeypatch, capsys):
    """If a response ever omits usage.cost, fall back to the per-token estimate
    rather than reporting a wrong/zero cost."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key-123")

    init_calls = []
    responses = [FakeResponse(usage=FakeUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000, cost=None))]
    monkeypatch.setattr(grok, "OpenAI", make_fake_openai_factory(responses, init_calls))

    grok.run(git_project, commit=False)

    expected = 1_000_000 / 1e6 * grok.PRICE_IN_PER_1M + 1_000_000 / 1e6 * grok.PRICE_OUT_PER_1M
    out = capsys.readouterr().out
    assert f"est_cost=${expected:.4f}" in out


def test_missing_openrouter_key_crashes_with_clear_message(git_project, monkeypatch, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    rc = grok.run(git_project, commit=False)

    assert rc == 1
    err = capsys.readouterr().err
    assert "OPENROUTER_API_KEY" in err
    assert "project-tracker" in err  # points at the right doppler project


def test_missing_openrouter_key_does_not_fall_back_to_xai_key(git_project, monkeypatch, capsys):
    """A missing OPENROUTER_API_KEY must crash even if XAI_API_KEY happens to
    be set in the environment -- no silent fallback to another provider's key."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "leftover-xai-key-should-be-ignored")

    rc = grok.run(git_project, commit=False)

    assert rc == 1
    err = capsys.readouterr().err
    assert "OPENROUTER_API_KEY" in err
    assert "leftover-xai-key-should-be-ignored" not in err
