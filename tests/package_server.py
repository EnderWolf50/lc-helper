"""A fake maalc-resource for the tests of src/lc_helper/package.py and startup.py: a dict of url -> bytes behind the
`fetch` argument, so no test touches the network."""

import hashlib
import json

from lc_helper import package

SOURCE = "https://example.test/pkg"
LICENCES = package.LICENCES


def sha(data):
    return hashlib.sha256(data).hexdigest()


def serve(version="2026.1.1", files=None, **manifest):
    """A fake server holding one package: {url: bytes} plus the manifest of its files."""
    files = files or {
        "data/event_table.json": b'{"events": []}',
        "data/gift_icons/9001.webp": b"gift-icon",
        "data/gift_icons/9002.webp": b"another-icon",
        "data/theme_packs.yaml": b"lc-helper never reads this",
        "image/Battle/BattleStart.png": b"start",
        "image/Map/Unused.png": b"unused",
    }
    body = {"version": version, "client": "9.9.9", "format": package.FORMAT, "template": package.TEMPLATE,
            "sources": [SOURCE], **manifest,
            "files": {p: {"size": len(d), "sha256": sha(d)} for p, d in sorted(files.items())}}
    served = {f"{SOURCE}/{version}/{p}": d for p, d in files.items()}
    served[f"{SOURCE}/{version}/manifest.json"] = json.dumps(body).encode()
    served[f"{SOURCE}/{version}/LICENSE"] = b"licence of " + version.encode()
    served[f"{SOURCE}/{version}/NOTICE.md"] = b"notice of " + version.encode()
    return served


class Server:
    def __init__(self, served):
        self.served, self.requests = served, []

    def __call__(self, url):
        self.requests.append(url)
        if url not in self.served:
            raise OSError(f"404 {url}")
        return self.served[url]

    def files(self):
        return [u for u in self.requests if not u.endswith(("manifest.json", "LICENSE", "NOTICE.md"))]
