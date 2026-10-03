"""Fixed-destination TCP relay for the isolated production SMTP path."""

from __future__ import annotations

import asyncio
import contextlib
import os


LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.getenv("SMTP_PROXY_LISTEN_PORT", "1587"))
TARGET_HOST = os.getenv("SMTP_PROXY_TARGET_HOST", "smtp.example.invalid")
TARGET_PORT = int(os.getenv("SMTP_PROXY_TARGET_PORT", "587"))
CONNECT_TIMEOUT = float(os.getenv("SMTP_PROXY_CONNECT_TIMEOUT", "5"))


async def _copy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while data := await reader.read(64 * 1024):
        writer.write(data)
        await writer.drain()


async def _close(writer: asyncio.StreamWriter) -> None:
    writer.close()
    with contextlib.suppress(ConnectionError, OSError):
        await writer.wait_closed()


async def relay(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
) -> None:
    try:
        upstream_reader, upstream_writer = await asyncio.wait_for(
            asyncio.open_connection(TARGET_HOST, TARGET_PORT),
            timeout=CONNECT_TIMEOUT,
        )
    except (TimeoutError, ConnectionError, OSError):
        await _close(client_writer)
        return

    try:
        await asyncio.gather(
            _copy(client_reader, upstream_writer),
            _copy(upstream_reader, client_writer),
        )
    except (ConnectionError, OSError):
        pass
    finally:
        await asyncio.gather(
            _close(client_writer),
            _close(upstream_writer),
            return_exceptions=True,
        )


async def main() -> None:
    server = await asyncio.start_server(relay, LISTEN_HOST, LISTEN_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
