from __future__ import annotations

import os
import socket
import threading


LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.getenv("SECURITY_LAB_PREVIEW_PORT", "8080"))
TARGET_HOST = os.getenv("SECURITY_LAB_PREVIEW_TARGET", "lab")
TARGET_PORT = int(os.getenv("SECURITY_LAB_PREVIEW_TARGET_PORT", "8000"))
TARGET_SOCKET = os.getenv("SECURITY_LAB_PREVIEW_SOCKET", "")


def _upstream() -> socket.socket:
    if TARGET_SOCKET:
        upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        upstream.settimeout(5)
        upstream.connect(TARGET_SOCKET)
        return upstream
    return socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=5)


def _copy(source: socket.socket, destination: socket.socket) -> None:
    try:
        while True:
            chunk = source.recv(65536)
            if not chunk:
                break
            destination.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            destination.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _handle(client: socket.socket) -> None:
    try:
        with _upstream() as upstream:
            incoming = threading.Thread(target=_copy, args=(client, upstream), daemon=True)
            outgoing = threading.Thread(target=_copy, args=(upstream, client), daemon=True)
            incoming.start()
            outgoing.start()
            incoming.join(timeout=30)
            outgoing.join(timeout=30)
    finally:
        client.close()


def main() -> None:
    with socket.create_server((LISTEN_HOST, LISTEN_PORT), reuse_port=False) as server:
        while True:
            client, _ = server.accept()
            threading.Thread(target=_handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
