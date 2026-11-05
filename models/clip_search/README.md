# 🖼️ clip_search: asking for pictures in Dutch

Describe an image in words, get it back. CLIP-style models make that easy in English. How much do
you lose in Dutch? This project measures it, then turns the result into a searchable demo.

Status: **pipeline tested, no real results yet.** See the [evaluation card](EVALUATION_CARD.md).

## The experiment

- **Same images, same categories, two languages.** All 80 COCO categories have [hand-written Dutch
  noun phrases](labels_nl.py). Relevance comes from COCO's human object labels, so no machine
  translation sits between the question and the answer.
- **English-only CLIP vs a multilingual text encoder** (`xlm-roberta-base-ViT-B-32`).
- **False friends.** Dutch `bank` is a couch, `boot` a boat, `beer` a bear, `motor` a motorcycle.
  An English-only model ought to fail these in a telling way.
- **Paired statistics.** mAP gap with a bootstrap over categories.
- **Degraded images.** JPEG artifacts, blur, downscaling, grayscale.

## Run it

```bash
pip install -e ".[vision,demo,dev]"
python -m clip_search.coco --out runs/coco           # about 1 GB
python -m clip_search.cli --coco runs/coco --out runs/clip \
    --model hf:openai/clip-vit-base-patch32 \
    --model openclip:xlm-roberta-base-ViT-B-32:laion5b_s13b_b90k
```

ViT-B/32 embeds COCO val quickly on a GPU and is workable on a laptop CPU. Add `--max-images 1000`
for a first pass.

## Demo and search integration

```bash
python -m clip_search.app --image-dir runs/coco/val2017 \
    --index-dir runs/clip/index/openclip_xlm-roberta-base-ViT-B-32_laion5b_s13b_b90k \
    --model openclip:xlm-roberta-base-ViT-B-32:laion5b_s13b_b90k

docker compose -f clip_search/docker-compose.yml up --build           # same demo, in a container
python -m clip_search.es_export --index-dir <index> --out runs/clip/bulk.ndjson  # for Elasticsearch
```

The container setup passes `docker compose config` but has not been built yet.
COCO images keep their own licences, so check them before hosting a public demo; a Space may be
better built on a CC0 image collection.
