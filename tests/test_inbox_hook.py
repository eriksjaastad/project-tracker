"""Tests for pt CLI inbox notification hook."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from scripts.pt import _notify_inbox


class TestNotifyInbox:
    """Tests for _notify_inbox()."""

    def test_skips_when_no_inbox_dir(self):
        """Should not create inbox dir — only writes if it exists."""
        with patch("socket.gethostname", return_value="MacBook-Pro.local"):
            with tempfile.TemporaryDirectory():
                # No inbox dir created
                _notify_inbox(1, "nonexistent-project", "Backlog", "Test task")
                # Should not crash

    def test_writes_notification(self):
        """Should write a kanban notification file."""
        with patch("socket.gethostname", return_value="MacBook-Pro.local"):
            with tempfile.TemporaryDirectory() as tmpdir:
                inbox = Path(tmpdir) / ".claude" / "inbox" / "test-project"
                inbox.mkdir(parents=True)
                with patch("os.path.expanduser", return_value=str(Path(tmpdir))):
                    _notify_inbox(42, "test-project", "In Progress", "Fix the bug")
                files = list(inbox.glob("*-kanban.md"))
                assert len(files) == 1
                content = files[0].read_text()
                assert "card_id: 42" in content
                assert "card_status: In Progress" in content
                assert "Fix the bug" in content
                assert "from: kanban" in content

    def test_rejects_path_traversal(self):
        """Should reject project IDs with path traversal characters."""
        with patch("socket.gethostname", return_value="MacBook-Pro.local"):
            with tempfile.TemporaryDirectory() as tmpdir:
                # Create the traversal target
                evil = Path(tmpdir) / ".claude" / "inbox" / "etcpasswd"
                evil.mkdir(parents=True)
                with patch("os.path.expanduser", return_value=str(Path(tmpdir))):
                    _notify_inbox(1, "../../etc/passwd", "Backlog", "evil")
                files = list(evil.glob("*.md"))
                assert len(files) == 0

    def test_includes_action_hint(self):
        """Should include appropriate action hint for each status."""
        with patch("socket.gethostname", return_value="MacBook-Pro.local"):
            with tempfile.TemporaryDirectory() as tmpdir:
                inbox = Path(tmpdir) / ".claude" / "inbox" / "myproj"
                inbox.mkdir(parents=True)
                with patch("os.path.expanduser", return_value=str(Path(tmpdir))):
                    _notify_inbox(99, "myproj", "To Do", "Do the thing")
                files = list(inbox.glob("*-kanban.md"))
                content = files[0].read_text()
                assert "pt tasks start 99" in content

    def test_writes_deleted_notification(self):
        """Should write a notification with Deleted status and action hint."""
        with patch("socket.gethostname", return_value="MacBook-Pro.local"):
            with tempfile.TemporaryDirectory() as tmpdir:
                inbox = Path(tmpdir) / ".claude" / "inbox" / "test-project"
                inbox.mkdir(parents=True)
                with patch("os.path.expanduser", return_value=str(Path(tmpdir))):
                    _notify_inbox(55, "test-project", "Deleted", "Old task to remove")
                files = list(inbox.glob("*-kanban.md"))
                assert len(files) == 1
                content = files[0].read_text()
                assert "card_id: 55" in content
                assert "card_status: Deleted" in content
                assert "Old task to remove" in content
                assert "permanently deleted" in content
