"""Process-local, page-by-page conditional GETs for PR evidence.

Every page is revalidated on every collection. Cached data is never a fallback
for failed authentication, a timeout, or malformed evidence. Callers reset the
inherited ``deadline`` before a collection; no cache survives process exit.
"""
from copy import deepcopy
from email.message import Message
import json
import re
import subprocess
import time
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

from scripts.pr_evidence import EvidenceError, GhaTransport


def _endpoint(value):
    if any(char in value for char in "\r\n"):
        raise EvidenceError("pagination", "Invalid control character in API endpoint")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise EvidenceError("pagination", "Malformed API pagination URL") from exc
    if (parsed.scheme or parsed.netloc) and (
        parsed.scheme != "https" or parsed.netloc != "api.github.com"
    ):
        raise EvidenceError("pagination", "Pagination must remain on api.github.com")
    path = parsed.path.lstrip("/")
    if (parsed.fragment or not path.startswith(("repos/", "users/"))
            or any(part in {".", ".."} for part in unquote(path).split("/"))):
        raise EvidenceError("pagination", "Expected a GitHub REST API endpoint")
    return path + ("?" + parsed.query if parsed.query else "")


def _response(raw):
    """Parse gha --include output for HTTP/1.x or HTTP/2, with CRLF or LF."""
    parts = re.split(r"\r?\n\r?\n", raw, maxsplit=1)
    lines = parts[0].splitlines()
    match = re.fullmatch(r"HTTP/\d(?:\.\d)? (\d{3})(?: .*)?", lines[0] if lines else "")
    if len(parts) != 2 or not match:
        raise EvidenceError("shape", "Missing valid GitHub HTTP response headers")
    headers = {}
    for line in lines[1:]:
        key, separator, value = line.partition(":")
        if not separator or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key):
            raise EvidenceError("shape", "Malformed GitHub HTTP header")
        key, value = key.lower(), value.strip()
        # Only these fields affect cached evidence or pagination. Unused
        # fields (including repeated Vary/Set-Cookie) need no normalization.
        if key not in {"etag", "link"}:
            continue
        if key in headers and key != "link":
            raise EvidenceError("shape", "Ambiguous duplicate GitHub HTTP header")
        headers[key] = headers[key] + ", " + value if key in headers else value
    return int(match[1]), headers, parts[1]


def _next_link(header, endpoint):
    next_links = []
    for entry in re.split(r",\s*(?=<)", header):
        match = re.fullmatch(r"\s*<([^<>]+)>\s*(;.*)\s*", entry)
        if not match:
            raise EvidenceError("pagination", "Malformed GitHub pagination Link")
        parameters = Message()
        parameters["content-type"] = "text/plain" + match[2]
        relation = parameters.get_param("rel")
        if not isinstance(relation, str):
            raise EvidenceError("pagination", "Pagination Link has no relation")
        if "next" in relation.split():
            target = _endpoint(match[1])
            if target.split("?", 1)[0] != endpoint.split("?", 1)[0]:
                raise EvidenceError("pagination", "Pagination changed API resource")
            next_links.append(target)
    if len(next_links) > 1:
        raise EvidenceError("pagination", "Ambiguous next page")
    return next_links[0] if next_links else None


def _overflow_page(endpoint, data):
    """A full terminal page needs a probe: a 304 can omit newly changed Links."""
    rows = data
    if isinstance(data, dict):
        rows = data.get("check_runs", data.get("workflows"))
    if not isinstance(rows, list):
        return None
    parsed = urlsplit(endpoint)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    parameters = dict(query)
    try:
        size = min(100, int(parameters.get("per_page", "30")))
        page = int(parameters.get("page", "1"))
    except ValueError as exc:
        raise EvidenceError("pagination", "Invalid numeric pagination parameter") from exc
    if size <= 0 or page <= 0:
        raise EvidenceError("pagination", "Pagination parameters must be positive")
    if len(rows) != size:
        return None
    query = [(key, value) for key, value in query if key != "page"]
    return parsed.path + "?" + urlencode([*query, ("page", str(page + 1))])


class ConditionalGhaTransport(GhaTransport):
    def __init__(self, cwd, *, run=None, deadline=None):
        super().__init__(cwd, run=run, deadline=deadline)
        self._cache = {}

    def _page(self, endpoint):
        previous = self._cache.get(endpoint)
        command = ["gha", "api", "--hostname", "github.com", "--method", "GET", "--include", "-H",
                   "Accept: application/vnd.github+json", endpoint]
        if previous:
            command += ["-H", f"If-None-Match: {previous[0]}"]
        remaining = 30 if self.deadline is None else self.deadline - time.monotonic()
        if remaining <= 0:
            raise EvidenceError("timeout", "Collection deadline elapsed")
        try:
            result = self.run(command, cwd=self.cwd, capture_output=True, text=True,
                              check=True, timeout=min(30, remaining))
            raw = result.stdout
        except subprocess.TimeoutExpired as exc:
            raise EvidenceError("timeout", "GitHub API request timed out") from exc
        except OSError as exc:
            raise EvidenceError("unavailable", "Cannot execute gha") from exc
        except subprocess.CalledProcessError as exc:
            # Parse only structured output; never echo credential-bearing stderr.
            try:
                raw = exc.stdout or ""
                status, _, body = _response(raw)
            except EvidenceError:
                raise EvidenceError("command", "GitHub API request failed") from exc
            if status == 404 and endpoint.endswith("/protection"):
                try:
                    value = json.loads(body)
                except ValueError:
                    value = None
                if isinstance(value, dict) and value.get("message") == "Branch not protected":
                    raise EvidenceError("not_protected", "Branch not protected", http_status=404) from exc
            if status != 304:  # gh reports 304 with a nonzero exit status.
                raise EvidenceError("http", "GitHub API request failed", http_status=status) from exc
        status, headers, body = _response(raw)
        if status == 304:
            if not previous or body.strip():
                raise EvidenceError("cache", "304 lacks cached evidence or contains a body")
            data, next_page = previous[1:]
        elif status == 200:
            try:
                data = json.loads(body)
            except ValueError as exc:
                raise EvidenceError("invalid_json", "GitHub API returned invalid JSON") from exc
            next_page = None
        else:
            raise EvidenceError("http", "Unexpected GitHub API status", http_status=status)
        if "link" in headers:
            next_page = _next_link(headers["link"], endpoint) if headers["link"] else None
        etag = headers.get("etag") or (previous[0] if status == 304 else None)
        if etag:
            self._cache[endpoint] = (etag, deepcopy(data), next_page)
        else:
            self._cache.pop(endpoint, None)
        return deepcopy(data), next_page

    def get(self, endpoint, *, paginate=False):
        endpoint, pages, seen = _endpoint(endpoint), [], set()
        while endpoint:
            if endpoint in seen:
                raise EvidenceError("pagination", "Pagination repeated a page")
            seen.add(endpoint)
            current = endpoint
            data, endpoint = self._page(current)
            if not paginate:
                return data
            pages.append(data)
            if endpoint is None:
                endpoint = _overflow_page(current, data)
        return pages
