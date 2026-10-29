"""HTTPS CONNECT proxy that only tunnels to allowlisted hosts.

Runs inside the proxy container. Usage: python proxy.py PORT HOST [HOST ...]
"""

import asyncio
import sys


async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def handle(client_reader, client_writer, allowed):
    try:
        request_line = (await client_reader.readline()).decode("latin-1").strip()
        while (await client_reader.readline()) not in (b"\r\n", b"\n", b""):
            pass

        method, target, _ = request_line.split(" ", 2)
        host, _, port = target.rpartition(":")
        if method != "CONNECT" or host not in allowed:
            print(f"DENY {request_line}", flush=True)
            client_writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            await client_writer.drain()
            client_writer.close()
            return

        upstream_reader, upstream_writer = await asyncio.open_connection(host, int(port))
        client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_writer.drain()
        await asyncio.gather(
            pipe(client_reader, upstream_writer),
            pipe(upstream_reader, client_writer),
        )
    except (ValueError, OSError):
        client_writer.close()


async def main(port, allowed):
    server = await asyncio.start_server(lambda r, w: handle(r, w, allowed), "0.0.0.0", port)
    print(f"proxy listening on {port}, allowing {sorted(allowed)}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), set(sys.argv[2:])))
