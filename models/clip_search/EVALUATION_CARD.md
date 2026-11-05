# Evaluation card: Dutch vs English image search

> **No results yet.** Hypotheses are registered here before the first run.

## What is evaluated

`openai/clip-vit-base-patch32` (English text encoder) and open_clip
`xlm-roberta-base-ViT-B-32` / `laion5b_s13b_b90k` (multilingual text encoder). Retrieval only,
no fine-tuning.

## Data

COCO val2017: 5000 images with human object labels. Annotations are CC BY 4.0, images keep their
individual Flickr licences (check the COCO terms); they're downloaded at run time and never
re-hosted from this repo.

Known limits: "contains the object" is a coarse relevance judgment. An image with a tiny bench in
the background counts. COCO images are everyday, Western-leaning Flickr photos from the 2010s, and
80 object nouns are far easier than real queries. So these numbers are upper bounds for practice.

## Pre-registered hypotheses (written before any run)

1. With English-only CLIP, Dutch queries lose mAP clearly (CI excludes zero).
2. With the multilingual encoder, the English-minus-Dutch gap is smaller, but not zero.
3. Cognates (`zebra`, `pizza`) show almost no gap. Unrelated words (`stoplicht`, `paraplu`) show
   the largest with English-only CLIP.
4. False friends fail on English-only CLIP: `beer` scores far below `a bear`.
5. Of the corruptions, downscaling or heavy JPEG hurts more than grayscale.

## Results

_Pending._ Copy curated tables to `results/clip_search/` and link them here.

## Next experiment

Longer natural-language queries, which need Dutch captions; machine-translated captions would add
translation error, so they should be reported as a separate condition.
