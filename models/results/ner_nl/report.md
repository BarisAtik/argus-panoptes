# Dutch NER study: results

Corpus: CoNLL-2002 Dutch, test split `ned.testb`, 119 articles. Commit 000e588, 2026-11-06T03:31:35+00:00. Intervals resample articles.

## All four labels (exact span and label)

| model | F1 | 95% CI | P | R |
| --- | --- | --- | --- | --- |
| gazetteer | 0.5825 | 0.550 to 0.615 | 0.8124 | 0.4539 |
| deduce | 0.2543 | 0.222 to 0.288 | 0.5889 | 0.1621 |
| nl_core_news_sm | 0.5274 | 0.495 to 0.560 | 0.5657 | 0.4940 |
| nl_core_news_md | 0.6111 | 0.583 to 0.641 | 0.6481 | 0.5780 |
| nl_core_news_lg | 0.6552 | 0.628 to 0.684 | 0.7243 | 0.5981 |
| own_aug_s0 | 0.8590 | 0.838 to 0.880 | 0.8677 | 0.8505 |
| own_aug_s1 | 0.8581 | 0.836 to 0.880 | 0.8677 | 0.8488 |
| own_aug_s2 | 0.8545 | 0.833 to 0.875 | 0.8597 | 0.8493 |
| own_s0 | 0.8346 | 0.811 to 0.859 | 0.8456 | 0.8239 |
| own_s1 | 0.8584 | 0.837 to 0.880 | 0.8672 | 0.8498 |
| own_s2 | 0.8570 | 0.836 to 0.878 | 0.8715 | 0.8429 |

## PER, LOC, ORG only (the fair cross-corpus view)

| model | F1 | 95% CI | P | R |
| --- | --- | --- | --- | --- |
| gazetteer | 0.5794 | 0.543 to 0.615 | 0.8503 | 0.4394 |
| deduce | 0.3329 | 0.296 to 0.369 | 0.5889 | 0.2320 |
| nl_core_news_sm | 0.5572 | 0.517 to 0.594 | 0.5664 | 0.5483 |
| nl_core_news_md | 0.6715 | 0.641 to 0.702 | 0.6909 | 0.6532 |
| nl_core_news_lg | 0.7037 | 0.674 to 0.733 | 0.7362 | 0.6739 |
| own_aug_s0 | 0.8790 | 0.857 to 0.900 | 0.8721 | 0.8860 |
| own_aug_s1 | 0.8762 | 0.854 to 0.898 | 0.8564 | 0.8969 |
| own_aug_s2 | 0.8755 | 0.854 to 0.897 | 0.8618 | 0.8896 |
| own_s0 | 0.8577 | 0.834 to 0.883 | 0.8357 | 0.8809 |
| own_s1 | 0.8806 | 0.861 to 0.902 | 0.8620 | 0.9001 |
| own_s2 | 0.8803 | 0.860 to 0.902 | 0.8805 | 0.8802 |

## Paired differences

| comparison | a | b | difference | low | high | p_value | n_clusters | p_holm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lg_vs_sm | 0.7037 | 0.5572 | 0.1465 | 0.1203 | 0.1741 | 0.0002 | 119 | 0.0010 |
| own_vs_lg | 0.8806 | 0.7037 | 0.1769 | 0.1405 | 0.2167 | 0.0002 | 119 | 0.0010 |
| own_vs_gazetteer | 0.8584 | 0.5825 | 0.2759 | 0.2459 | 0.3056 | 0.0002 | 119 | 0.0010 |
| aug_vs_own_clean | 0.8581 | 0.8584 | -0.0003 | -0.0093 | 0.0085 | 0.9328 | 119 | 0.9328 |
| aug_vs_own_transcript | 0.7007 | 0.0076 | 0.6931 | 0.6515 | 0.7290 | 0.0002 | 119 | 0.0010 |

## Robustness

| model | condition | clean F1 | changed F1 | loss | 95% CI changed |
| --- | --- | --- | --- | --- | --- |
| nl_core_news_lg | lowercase | 0.7037 | 0.4669 | 0.2368 | 0.429 to 0.505 |
| nl_core_news_lg | transcript | 0.7037 | 0.4207 | 0.2830 | 0.378 to 0.465 |
| own_s1 | lowercase | 0.8806 | 0.0116 | 0.8691 | 0.003 to 0.023 |
| own_s1 | transcript | 0.8806 | 0.0108 | 0.8698 | 0.002 to 0.022 |
| own_aug_s1 | lowercase | 0.8762 | 0.7040 | 0.1722 | 0.671 to 0.735 |
| own_aug_s1 | transcript | 0.8762 | 0.7101 | 0.1661 | 0.657 to 0.755 |

## Recall by whether the entity string occurred in training

| model | seen_mentions | unseen_mentions | recall_seen | recall_unseen | gap |
| --- | --- | --- | --- | --- | --- |
| gazetteer | 1804 | 2137 | 0.9917 | 0.0000 | 0.9917 |
| nl_core_news_lg | 1804 | 2137 | 0.6702 | 0.5372 | 0.1330 |
| own_s1 | 1804 | 2137 | 0.9446 | 0.7698 | 0.1748 |

## Person-name tokens a redactor would leave visible

| model | condition | name tokens | share unmasked | 95% CI |
| --- | --- | --- | --- | --- |
| nl_core_news_sm | clean | 1905 | 0.1890 | 0.148 to 0.230 |
| nl_core_news_sm | transcript | 1905 | 0.7848 | 0.747 to 0.823 |
| nl_core_news_md | clean | 1905 | 0.0987 | 0.074 to 0.127 |
| nl_core_news_md | transcript | 1905 | 0.5559 | 0.508 to 0.600 |
| nl_core_news_lg | clean | 1905 | 0.0866 | 0.064 to 0.115 |
| nl_core_news_lg | transcript | 1905 | 0.4383 | 0.393 to 0.481 |
| deduce | clean | 1905 | 0.2740 | 0.235 to 0.315 |
| deduce | transcript | 1905 | 1.0000 | 1.000 to 1.000 |

## Calibration of span confidence

| model | condition | calibration | temperature | spans | precision | mean_confidence | ece | threshold_for_dev_95 | test_coverage_at_threshold | test_precision_at_threshold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| own_s1 | clean | raw | 1.0000 | 3862 | 0.8672 | 0.9070 | 0.0401 | 0.8219 | 0.8086 | 0.9446 |
| own_s1 | clean | scaled | 1.4142 | 3862 | 0.8672 | 0.8537 | 0.0166 | 0.7043 | 0.8035 | 0.9462 |
| own_s1 | transcript | raw | 1.0000 | 15 | 1.0000 | 0.8433 | 0.1567 | 0.8219 | 0.7333 | 1.0000 |
| own_s1 | transcript | scaled | 1.4142 | 15 | 1.0000 | 0.7523 | 0.2477 | 0.7043 | 0.6667 | 1.0000 |
| own_aug_s1 | clean | raw | 1.0000 | 3855 | 0.8677 | 0.9139 | 0.0462 | 0.8519 | 0.8010 | 0.9443 |
| own_aug_s1 | clean | scaled | 1.4142 | 3855 | 0.8677 | 0.8685 | 0.0091 | 0.7336 | 0.8010 | 0.9456 |
| own_aug_s1 | transcript | raw | 1.0000 | 3435 | 0.7523 | 0.8203 | 0.0681 | 0.8519 | 0.5863 | 0.9106 |
| own_aug_s1 | transcript | scaled | 1.4142 | 3435 | 0.7523 | 0.7452 | 0.0261 | 0.7336 | 0.5694 | 0.9075 |

## Name swap

| model | metric | group | recall | mentions |
| --- | --- | --- | --- | --- |
| nl_core_news_sm | exact | dutch | 0.5164 | 5490 |
| nl_core_news_sm | exact | hindustani | 0.4774 | 5490 |
| nl_core_news_sm | exact | moroccan | 0.3719 | 5490 |
| nl_core_news_sm | exact | polish | 0.4510 | 5490 |
| nl_core_news_sm | exact | turkish | 0.5714 | 5490 |
| nl_core_news_md | exact | dutch | 0.7872 | 5490 |
| nl_core_news_md | exact | hindustani | 0.4623 | 5490 |
| nl_core_news_md | exact | moroccan | 0.7776 | 5490 |
| nl_core_news_md | exact | polish | 0.7169 | 5490 |
| nl_core_news_md | exact | turkish | 0.5951 | 5490 |
| nl_core_news_lg | exact | dutch | 0.8709 | 5490 |
| nl_core_news_lg | exact | hindustani | 0.4628 | 5490 |
| nl_core_news_lg | exact | moroccan | 0.7617 | 5490 |
| nl_core_news_lg | exact | polish | 0.7723 | 5490 |
| nl_core_news_lg | exact | turkish | 0.5732 | 5490 |
| deduce | exact | dutch | 0.8851 | 5490 |
| deduce | exact | hindustani | 0.7909 | 5490 |
| deduce | exact | moroccan | 0.7372 | 5490 |
| deduce | exact | polish | 0.4852 | 5490 |
| deduce | exact | turkish | 0.7638 | 5490 |
| own_s1 | exact | dutch | 0.9740 | 5490 |
| own_s1 | exact | hindustani | 0.8858 | 5490 |
| own_s1 | exact | moroccan | 0.9475 | 5490 |
| own_s1 | exact | polish | 0.9599 | 5490 |
| own_s1 | exact | turkish | 0.9390 | 5490 |
| own_aug_s1 | exact | dutch | 0.9749 | 5490 |
| own_aug_s1 | exact | hindustani | 0.9341 | 5490 |
| own_aug_s1 | exact | moroccan | 0.9648 | 5490 |
| own_aug_s1 | exact | polish | 0.9692 | 5490 |
| own_aug_s1 | exact | turkish | 0.9690 | 5490 |
| nl_core_news_sm | any_overlap | dutch | 0.7401 | 5490 |
| nl_core_news_sm | any_overlap | hindustani | 0.8166 | 5490 |
| nl_core_news_sm | any_overlap | moroccan | 0.8570 | 5490 |
| nl_core_news_sm | any_overlap | polish | 0.7466 | 5490 |
| nl_core_news_sm | any_overlap | turkish | 0.7679 | 5490 |
| nl_core_news_md | any_overlap | dutch | 0.8945 | 5490 |
| nl_core_news_md | any_overlap | hindustani | 0.9005 | 5490 |
| nl_core_news_md | any_overlap | moroccan | 0.9776 | 5490 |
| nl_core_news_md | any_overlap | polish | 0.8920 | 5490 |
| nl_core_news_md | any_overlap | turkish | 0.8829 | 5490 |
| nl_core_news_lg | any_overlap | dutch | 0.9299 | 5490 |
| nl_core_news_lg | any_overlap | hindustani | 0.8306 | 5490 |
| nl_core_news_lg | any_overlap | moroccan | 0.9474 | 5490 |
| nl_core_news_lg | any_overlap | polish | 0.9155 | 5490 |
| nl_core_news_lg | any_overlap | turkish | 0.9077 | 5490 |
| deduce | any_overlap | dutch | 1.0000 | 5490 |
| deduce | any_overlap | hindustani | 0.8887 | 5490 |
| deduce | any_overlap | moroccan | 0.8373 | 5490 |
| deduce | any_overlap | polish | 0.5563 | 5490 |
| deduce | any_overlap | turkish | 0.8579 | 5490 |
| own_s1 | any_overlap | dutch | 0.9967 | 5490 |
| own_s1 | any_overlap | hindustani | 0.9863 | 5490 |
| own_s1 | any_overlap | moroccan | 0.9954 | 5490 |
| own_s1 | any_overlap | polish | 0.9940 | 5490 |
| own_s1 | any_overlap | turkish | 0.9974 | 5490 |
| own_aug_s1 | any_overlap | dutch | 0.9980 | 5490 |
| own_aug_s1 | any_overlap | hindustani | 0.9953 | 5490 |
| own_aug_s1 | any_overlap | moroccan | 0.9984 | 5490 |
| own_aug_s1 | any_overlap | polish | 0.9980 | 5490 |
| own_aug_s1 | any_overlap | turkish | 0.9984 | 5490 |

## Why names get lost (post hoc)

| model | group | fully_masked | top_labels |
| --- | --- | --- | --- |
| nl_core_news_md | dutch | 0.8862 | PERSON 0.81, none 0.11, GPE 0.07, WORK_OF_ART 0.01 |
| nl_core_news_md | turkish | 0.7372 | PERSON 0.68, GPE 0.10, none 0.09, ORG 0.05 |
| nl_core_news_md | moroccan | 0.9184 | PERSON 0.83, GPE 0.10, ORG 0.03, none 0.02 |
| nl_core_news_md | polish | 0.8197 | PERSON 0.76, none 0.10, GPE 0.05, NORP 0.04 |
| nl_core_news_md | hindustani | 0.6801 | PERSON 0.52, ORG 0.18, none 0.10, WORK_OF_ART 0.05 |
| nl_core_news_lg | dutch | 0.9250 | PERSON 0.89, none 0.07, ORG 0.03, GPE 0.01 |
| nl_core_news_lg | turkish | 0.7953 | PERSON 0.65, ORG 0.20, none 0.09, GPE 0.05 |
| nl_core_news_lg | moroccan | 0.8867 | PERSON 0.81, GPE 0.07, none 0.05, ORG 0.04 |
| nl_core_news_lg | polish | 0.9004 | PERSON 0.80, ORG 0.10, none 0.08, GPE 0.01 |
| nl_core_news_lg | hindustani | 0.6998 | PERSON 0.50, none 0.17, ORG 0.15, GPE 0.09 |

## Original person names, for reference

| model | original_person_recall |
| --- | --- |
| nl_core_news_sm | 0.5956 |
| nl_core_news_md | 0.7495 |
| nl_core_news_lg | 0.7559 |
| deduce | 0.5264 |
| own_s1 | 0.9308 |
| own_aug_s1 | 0.9399 |
