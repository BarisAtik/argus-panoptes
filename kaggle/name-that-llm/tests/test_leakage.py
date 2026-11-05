from ntl.data import ID, LABEL, TEXT
from ntl.leakage import (
    adversarial_validation,
    cluster_shape,
    duplicate_text,
    id_order_signal,
    identity_mentions,
    length_signal,
)
from ntl.leakage import (
    test_prompt_overlap as prompt_overlap,
)


def test_duplicates_with_conflicting_labels_are_found(small):
    train, _, _ = small
    bad = train.copy()
    bad.loc[1, TEXT] = bad.loc[0, TEXT].upper()
    report = duplicate_text(bad)
    assert report["duplicated_rows"] == 2
    if bad.loc[0, LABEL] != bad.loc[1, LABEL]:
        assert report["conflicting_label_groups"] == 1


def test_identity_mentions_catches_self_naming(small):
    train, _, _ = small
    bad = train.copy()
    bad.loc[:9, TEXT] = bad.loc[:9, LABEL].str.split("-").str[0] + " wrote this."
    assert identity_mentions(bad)["share_rows_with_token"] >= 10 / len(bad)


def test_id_order_flags_sorted_files(small):
    train, _, _ = small
    leaky = train.sort_values(LABEL).reset_index(drop=True)
    leaky[ID] = [f"x{i}" for i in range(len(leaky))]
    assert id_order_signal(leaky)["accuracy"] > 0.8
    clean = id_order_signal(train)
    assert clean["accuracy"] < 3 * clean["chance"]


def test_length_signal_near_zero_on_uninformative_length(small):
    train, _, _ = small
    assert length_signal(train)["eta_squared"] < 0.15


def test_prompt_overlap_separates_seen_from_unseen(small):
    train, test, _ = small
    assert prompt_overlap(train, test)["looks_unseen"]
    copied = train.sample(100, random_state=0)[[ID, TEXT]]
    assert not prompt_overlap(train, copied)["looks_unseen"]


def test_clean_data_has_no_duplicates(small):
    """Regression: filtering to zero rows and then assigning used to resurrect every row."""
    train, _, _ = small
    assert duplicate_text(train)["duplicated_rows"] == 0


def test_adversarial_validation_quiet_on_same_source(small):
    """Regression: without prompt grouping and masking this scored 0.99 on identical sources."""
    train, test, _ = small
    assert adversarial_validation(train, test)["auc"] < 0.7


def test_adversarial_validation_fires_on_style_drift(small):
    train, test, _ = small
    drifted = test.assign(text=test["text"].str.replace(". ", "! ", regex=False) + " Thanks!")
    assert adversarial_validation(train, drifted)["auc"] > 0.9


def test_cluster_shape_reports_a_grid(small):
    _, test, _ = small
    shape = cluster_shape(test, 18)
    assert shape["n_clusters"] == 10 and shape["share_rows_in_full_clusters"] == 1.0
