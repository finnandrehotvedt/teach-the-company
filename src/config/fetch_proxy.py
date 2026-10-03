from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import ssl
import stat
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn, UnixStreamServer
from urllib.parse import urljoin, urlsplit


MAX_REQUEST_BYTES = 4096
MAX_REMOTE_BYTES = 1_000_000
MAX_REDIRECTS = 4
SUPPORTED_TYPES = {"text/html", "text/plain", "text/markdown", "application/json"}


class FetchError(Exception):
    pass


def resolve_public_target(url: str) -> tuple[object, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise FetchError("Use a public HTTP or HTTPS link without embedded credentials.")
    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise FetchError("Use a valid public HTTP or HTTPS link.") from exc
    if parsed_port not in {None, 80, 443}:
        raise FetchError("Public links must use the standard HTTP or HTTPS port.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        candidates = {
            item[4][0]
            for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise FetchError("The link hostname could not be resolved.") from exc
    if not candidates:
        raise FetchError("The link hostname could not be resolved.")
    addresses = [ipaddress.ip_address(item) for item in candidates]
    if any(not address.is_global for address in addresses):
        raise FetchError("Private, local and reserved network addresses are blocked.")
    return parsed, str(sorted(addresses, key=lambda item: (item.version, str(item)))[0])


class PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, pinned_ip: str, port: int, timeout: int):
        self.pinned_ip = pinned_ip
        super().__init__(host, port=port, timeout=timeout)

    def connect(self):
        self.sock = socket.create_connection((self.pinned_ip, self.port), self.timeout)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, pinned_ip: str, port: int, timeout: int):
        self.pinned_ip = pinned_ip
        super().__init__(host, port=port, timeout=timeout, context=ssl.create_default_context())

    def connect(self):
        raw_socket = socket.create_connection((self.pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


def _safe_validator(value: str) -> str:
    value = value.strip()[:500]
    if "\r" in value or "\n" in value:
        raise FetchError("Invalid conditional request validator.")
    return value


def fetch(url: str, *, etag: str = "", last_modified: str = "") -> dict[str, object]:
    current = url
    etag = _safe_validator(etag)
    last_modified = _safe_validator(last_modified)
    for redirect_number in range(MAX_REDIRECTS + 1):
        parsed, pinned_ip = resolve_public_target(current)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        connection_class = PinnedHTTPSConnection if parsed.scheme == "https" else PinnedHTTPConnection
        connection = connection_class(parsed.hostname, pinned_ip, port, timeout=6)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        try:
            request_headers = {
                "Accept": "text/html,text/plain,application/json,text/markdown;q=0.9",
                "Accept-Encoding": "identity",
                "User-Agent": "TeachTheCompany-LinkReader/1.0 (+https://teachthecompany.com)",
            }
            if current == url and etag:
                request_headers["If-None-Match"] = etag
            if current == url and last_modified:
                request_headers["If-Modified-Since"] = last_modified
            connection.request(
                "GET",
                path,
                headers=request_headers,
            )
            response = connection.getresponse()
            if response.status == 304:
                return {
                    "body": "",
                    "content_type": "text/plain",
                    "final_url": current,
                    "not_modified": True,
                    "etag": _safe_validator(response.getheader("ETag", etag)),
                    "last_modified": _safe_validator(response.getheader("Last-Modified", last_modified)),
                }
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location or redirect_number >= MAX_REDIRECTS:
                    raise FetchError("The link redirected too many times.")
                current = urljoin(current, location)
                continue
            if not 200 <= response.status < 300:
                raise FetchError("The public page did not return a successful response.")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise FetchError("Compressed responses are not accepted by the safe link reader.")
            content_type = response.headers.get_content_type()
            if content_type not in SUPPORTED_TYPES:
                raise FetchError("That link is not a supported text page.")
            content_length = response.getheader("Content-Length")
            if content_length and int(content_length) > MAX_REMOTE_BYTES:
                raise FetchError("That page is too large to learn in one lesson.")
            body = response.read(MAX_REMOTE_BYTES + 1)
            if len(body) > MAX_REMOTE_BYTES:
                raise FetchError("That page is too large to learn in one lesson.")
            charset = response.headers.get_content_charset() or "utf-8"
            return {
                "body": body.decode(charset, errors="replace"),
                "content_type": content_type,
                "final_url": current,
                "not_modified": False,
                "etag": _safe_validator(response.getheader("ETag", "")),
                "last_modified": _safe_validator(response.getheader("Last-Modified", "")),
            }
        except FetchError:
            raise
        except (OSError, ssl.SSLError, http.client.HTTPException, ValueError) as exc:
            raise FetchError("The link could not be read safely right now.") from exc
        finally:
            connection.close()
    raise FetchError("The link redirected too many times.")


class Handler(BaseHTTPRequestHandler):
    server_version = "TeachLinkReader/1.0"

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "Not found."})

    def do_POST(self):
        if self.path != "/fetch":
            self._json(404, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 2 or length > MAX_REQUEST_BYTES:
            self._json(400, {"error": "Invalid request size."})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            etag = payload.get("etag", "")
            last_modified = payload.get("last_modified", "")
            if not isinstance(etag, str) or not isinstance(last_modified, str):
                raise TypeError
            result = fetch(payload["url"], etag=etag, last_modified=last_modified)
        except (json.JSONDecodeError, KeyError, TypeError):
            self._json(400, {"error": "A URL is required."})
        except FetchError as exc:
            self._json(422, {"error": str(exc)})
        else:
            self._json(200, result)

    def log_message(self, format, *args):
        return


class ThreadingUnixHTTPServer(ThreadingMixIn, UnixStreamServer):
    daemon_threads = True


def main() -> None:
    socket_value = os.getenv("FETCH_PROXY_SOCKET", "").strip()
    if socket_value:
        socket_path = Path(socket_value)
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        if socket_path.exists():
            if not stat.S_ISSOCK(socket_path.stat().st_mode):
                raise SystemExit("Refusing to replace a non-socket fetch-proxy path")
            socket_path.unlink()
        server = ThreadingUnixHTTPServer(str(socket_path), Handler)
        os.chmod(socket_path, 0o660)
        server.serve_forever()
        return
    host = os.getenv("FETCH_PROXY_LISTEN_HOST", "0.0.0.0")
    port = int(os.getenv("FETCH_PROXY_LISTEN_PORT", "8081"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
