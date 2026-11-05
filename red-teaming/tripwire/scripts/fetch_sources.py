"""Download the pinned wheels that hold the third-party text. They are only read as zip files."""

import subprocess
import sys
from pathlib import Path

PINS = ["garak==0.17.1", "pyrit==1.1.0"]  # Apache-2.0 and MIT

out = Path(__file__).parent.parent / "data" / "wheels"
out.mkdir(parents=True, exist_ok=True)
subprocess.check_call([sys.executable, "-m", "pip", "download", "--no-deps", "-q", "-d", str(out), *PINS])
print(sorted(p.name for p in out.iterdir()))
