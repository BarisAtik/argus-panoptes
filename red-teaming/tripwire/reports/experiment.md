# Tripwire experiment

Generated from `experiment.json`. 3 seeds, 1500 positive training documents. Thresholds come from validation data in the training sources, aiming for 1% FPR. Numbers are means over seeds. Per-seed values and template-bootstrap intervals are in the JSON.

## Data audit

- 362 payloads, 357 unique, from only **74 templates**, so the effective sample is far smaller than the document count.
- In a naive random split, 94.0% of positive test documents carry a payload that also appears in training.
- The regex fires on 0.0% of benign text in every source, so its false positives are not the problem. Its recall is.

## By split

| Split | Model | AUROC | Recall at threshold | FPR at threshold | Recall at 1% FPR (oracle) |
| --- | --- | ---: | ---: | ---: | ---: |
| naive (shared templates) | regex | 0.584 | 16.8% | 0.0% | 16.8% |
| naive (shared templates) | tfidf_lr | 0.998 | 95.3% | 1.5% | 96.0% |
| naive (shared templates) | byte_cnn | 0.993 | 93.5% | 1.0% | 92.0% |
| bare payloads in training | regex | 0.542 | 8.3% | 0.0% | 8.3% |
| bare payloads in training | tfidf_lr | 0.992 | 77.5% | 0.1% | 90.1% |
| bare payloads in training | byte_cnn | 0.960 | 74.9% | 0.8% | 79.0% |
| grouped templates | regex | 0.542 | 8.3% | 0.0% | 8.3% |
| grouped templates | tfidf_lr | 0.996 | 94.3% | 0.5% | 95.6% |
| grouped templates | byte_cnn | 0.994 | 93.1% | 1.1% | 92.7% |
| leave one source out | regex | 0.625 | 25.1% | 0.0% | 25.1% |
| leave one source out | tfidf_lr | 0.883 | 63.7% | 10.0% | 47.8% |
| leave one source out | byte_cnn | 0.833 | 58.2% | 10.6% | 38.0% |

## By held-out source

| Held-out attack source | CNN recall | CNN FPR | TF-IDF recall | TF-IDF FPR | Regex recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| agentdojo | 69.7% | 7.3% | 65.6% | 7.7% | 20.0% |
| garak_latent | 35.8% | 9.7% | 50.9% | 8.9% | 2.4% |
| promptinject | 92.8% | 10.3% | 95.3% | 11.8% | 51.1% |
| pyrit_sysprompt | 34.4% | 15.1% | 42.8% | 11.6% | 26.9% |

| Held-out benign source | CNN recall | CNN FPR | TF-IDF recall | TF-IDF FPR |
| --- | ---: | ---: | ---: | ---: |
| dojo_env | 55.7% | 7.7% | 70.4% | 17.1% |
| garak_contexts | 56.9% | 12.0% | 59.0% | 6.2% |
| pkg_docs | 61.9% | 12.1% | 61.6% | 6.7% |

## Recall under rewriting

3 seeds, grouped splits, threshold fixed on clean validation data. Augmented models trained on upper, zero_width, homoglyph. Never trained on: spaced, leet, synonym, base64.

| Detector | none | upper | zero_width | homoglyph | spaced | leet | synonym | base64 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| regex/plain | 8% | 8% | 0% | 0% | 0% | 0% | 1% | 0% |
| regex/normalised | 8% | 8% | 8% | 8% | 0% | 0% | 1% | 0% |
| tfidf_lr/plain | 93% | 93% | 66% | 19% | 0% | 1% | 85% | 0% |
| tfidf_lr/normalised | 93% | 93% | 93% | 93% | 89% | 1% | 85% | 0% |
| tfidf_lr/canonical | 93% | 93% | 93% | 93% | 89% | 1% | 85% | 0% |
| tfidf_lr/augmented | 94% | 94% | 98% | 98% | 2% | 4% | 87% | 0% |
| tfidf_lr/augmented+normalised | 93% | 93% | 93% | 93% | 89% | 1% | 85% | 0% |
| byte_cnn/plain | 93% | 91% | 72% | 53% | 12% | 53% | 86% | 74% |
| byte_cnn/normalised | 93% | 91% | 93% | 93% | 58% | 53% | 86% | 76% |
| byte_cnn/canonical | 92% | 92% | 92% | 92% | 59% | 57% | 85% | 35% |
| byte_cnn/augmented | 78% | 99% | 100% | 100% | 12% | 47% | 66% | 81% |
| byte_cnn/augmented+normalised | 87% | 99% | 86% | 87% | 49% | 45% | 79% | 77% |

False-positive rate when the same rewrite is applied to benign documents:

| Detector | none | upper | zero_width | homoglyph | spaced | leet | synonym | base64 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| regex/plain | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| regex/normalised | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| tfidf_lr/plain | 0.5% | 0.5% | 0.6% | 0.0% | 0.0% | 0.0% | 0.2% | 0.0% |
| tfidf_lr/normalised | 0.5% | 0.5% | 0.5% | 0.5% | 0.3% | 0.0% | 0.3% | 0.0% |
| tfidf_lr/canonical | 0.5% | 0.5% | 0.5% | 0.5% | 0.3% | 0.0% | 0.3% | 0.0% |
| tfidf_lr/augmented | 0.7% | 0.7% | 93.3% | 82.2% | 0.0% | 0.0% | 0.3% | 0.0% |
| tfidf_lr/augmented+normalised | 0.5% | 0.5% | 0.5% | 0.5% | 0.3% | 0.0% | 0.2% | 0.0% |
| byte_cnn/plain | 1.2% | 80.0% | 2.1% | 5.5% | 0.0% | 3.3% | 1.2% | 87.3% |
| byte_cnn/normalised | 1.6% | 81.1% | 1.5% | 1.6% | 0.0% | 4.5% | 1.4% | 87.7% |
| byte_cnn/canonical | 0.9% | 0.9% | 0.8% | 0.9% | 0.0% | 1.9% | 0.7% | 30.9% |
| byte_cnn/augmented | 0.7% | 99.5% | 99.9% | 99.9% | 0.0% | 1.9% | 0.7% | 92.7% |
| byte_cnn/augmented+normalised | 0.7% | 99.6% | 0.7% | 0.7% | 0.0% | 1.1% | 0.8% | 90.3% |
