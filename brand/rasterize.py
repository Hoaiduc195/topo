"""Export the logo PNGs with a real browser engine.

Serves brand/ on 127.0.0.1 and saves PNGs that brand/rasterize.html posts back into brand/logo/png/.
Run it, open http://127.0.0.1:4182/rasterize.html, and wait for "done". Then build favicon.ico:

    python3 -I brand/rasterize.py            # serve
    python3 -I brand/rasterize.py ico        # pack favicon-16/32/48.png into favicon.ico
"""
import re
import struct
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "logo" / "png"
NAME = re.compile(r"^/save/([a-z0-9-]+(?:@2x)?\.png)$")


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        m = NAME.match(self.path)
        if not m:
            self.send_error(400, "expected /save/<name>.png")
            return
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if not data.startswith(b"\x89PNG"):
            self.send_error(400, "not a PNG")
            return
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / m.group(1)).write_bytes(data)
        self.send_response(204)
        self.end_headers()


def pack_ico(sizes=(16, 32, 48)):
    """An ICO holding PNG images, which every current browser reads."""
    pngs = [(OUT / f"favicon-{s}.png").read_bytes() for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for s, png in zip(sizes, pngs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blobs += png
    (ROOT / "logo" / "favicon.ico").write_bytes(header + entries + blobs)
    print("wrote", ROOT / "logo" / "favicon.ico")


if __name__ == "__main__":
    if sys.argv[1:] == ["ico"]:
        pack_ico()
    else:
        ThreadingHTTPServer(("127.0.0.1", 4182), partial(Handler, directory=str(ROOT))).serve_forever()
