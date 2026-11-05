"""COCO val2017: 5000 images with human object labels (about 1 GB).

Annotations are CC BY 4.0; images keep their individual Flickr licences. So they are downloaded
at run time and never stored or re-hosted here. Check cocodataset.org/#termsofuse before
publishing a demo that shows them.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

IMAGES_URL = "http://images.cocodataset.org/zips/val2017.zip"
ANNOTATIONS_URL = "http://images.cocodataset.org/annotations/annotations_trainval2017.zip"


def load_annotations(path: str | Path) -> tuple[list[str], dict[str, np.ndarray], list[int]]:
    """Return (file names, {category name: boolean per image}, image ids)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    images = sorted(data["images"], key=lambda i: i["id"])
    position = {image["id"]: index for index, image in enumerate(images)}
    categories = {c["id"]: c["name"] for c in data["categories"]}
    relevance = {name: np.zeros(len(images), dtype=bool) for name in categories.values()}
    for annotation in data["annotations"]:
        if annotation["image_id"] in position:
            name = categories[annotation["category_id"]]
            relevance[name][position[annotation["image_id"]]] = True
    return [i["file_name"] for i in images], relevance, [i["id"] for i in images]


def download(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for url in (ANNOTATIONS_URL, IMAGES_URL):
        target = out / url.rsplit("/", 1)[-1]
        if not target.exists():
            print(f"Downloading {url}", flush=True)
            urllib.request.urlretrieve(url, target)
        with zipfile.ZipFile(target) as archive:
            archive.extractall(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("runs/coco"))
    download(parser.parse_args().out)
