"""Download a torch-free multilingual-e5-small, for when Hugging Face is out of reach.

Hugging Face remains the normal route: `beacon ingest --embedder st:intfloat/multilingual-e5-small`.
This one takes the int8 ONNX export from the npm package `dsh-plugin-discover-model`, a third
party's repackaging of `Xenova/multilingual-e5-small`. Weights from a stranger deserve care,
so the tarball hash is pinned, and only three data files are read from it. No code in the package
is run. Compare `model_quantized.onnx` with the SHA-256 shown on the Hugging Face file page
before you trust the output for anything real.
"""

from __future__ import annotations

import hashlib
import tarfile
import tempfile
from pathlib import Path

import httpx

TARBALL = "https://registry.npmjs.org/dsh-plugin-discover-model/-/dsh-plugin-discover-model-0.1.0.tgz"
TARBALL_SHA256 = "607185cd0c99cf566541a30bf7b2a15d608594018d1caa93a79b74bb5def5199"
FILES = {
    "model_quantized.onnx": "f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193",
    "tokenizer.json": "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
}
DEFAULT_DIRECTORY = "data/models/multilingual-e5-small"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def extract(tarball: Path, directory: Path) -> None:
    """Copy the expected files out by exact name, checking each hash. Nothing else is touched."""
    directory.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball) as archive:
        for name, expected in FILES.items():
            member = archive.extractfile(f"package/{name}")
            if member is None:
                raise ValueError(f"{name} is not a regular file in the archive")
            target = directory / name
            partial = target.with_suffix(target.suffix + ".part")
            with open(partial, "wb") as handle:
                while block := member.read(1 << 20):
                    handle.write(block)
            if sha256(partial) != expected:
                partial.unlink()
                raise ValueError(f"hash mismatch for {name}")
            partial.replace(target)


def fetch(directory: str | Path = DEFAULT_DIRECTORY) -> Path:
    directory = Path(directory)
    if all((directory / n).is_file() and sha256(directory / n) == h for n, h in FILES.items()):
        return directory
    with tempfile.TemporaryDirectory() as scratch:
        tarball = Path(scratch) / "model.tgz"
        with httpx.stream("GET", TARBALL, timeout=600, follow_redirects=True) as response:
            response.raise_for_status()
            with open(tarball, "wb") as handle:
                for block in response.iter_bytes():
                    handle.write(block)
        if sha256(tarball) != TARBALL_SHA256:
            raise ValueError("tarball hash mismatch; refusing to read it")
        extract(tarball, directory)
    return directory
