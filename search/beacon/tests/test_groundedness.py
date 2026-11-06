import numpy as np

from beacon.groundedness import Thresholds, check_answer, check_claim, split_claims

PASSAGE = (
    "De aanbieder moet logbestanden minimaal 6 maanden bewaren. "
    "Een organisatie kan ervoor kiezen om een extern bureau in te schakelen."
)


def test_split_claims_keeps_citations():
    claims = split_claims("Logbestanden blijven bewaard [1]. Dat is verplicht [2]. [3]")
    assert claims == [("Logbestanden blijven bewaard", [1]), ("Dat is verplicht", [2, 3])]


def test_faithful_claim_passes():
    assert check_claim("De aanbieder moet logbestanden bewaren", [PASSAGE]).supported


def test_changed_number_is_flagged():
    check = check_claim("De aanbieder moet logbestanden minimaal 9 maanden bewaren", [PASSAGE])
    assert not check.supported
    assert "number" in check.reasons[0]


def test_flipped_negation_is_flagged():
    check = check_claim("De aanbieder hoeft logbestanden niet te bewaren", [PASSAGE])
    assert any("negation" in reason for reason in check.reasons)


def test_can_turned_into_must_is_flagged():
    strict = Thresholds(check_modality=True)
    check = check_claim("Een organisatie moet een extern bureau inschakelen", [PASSAGE], strict)
    assert any("weaker" in reason for reason in check.reasons)


def test_unknown_terms_are_flagged():
    assert not check_claim("Quantumcomputers versnellen trainingsdata enorm", [PASSAGE]).supported


def test_law_not_in_source_is_flagged():
    check = check_claim("De aanbieder moet logbestanden bewaren volgens artikel 5 AVG", [PASSAGE])
    assert any("citation" in reason for reason in check.reasons)


def test_claim_without_citation_is_unsupported():
    checks = check_answer("Logbestanden blijven bewaard.", [PASSAGE])
    assert not checks[0].supported
    assert checks[0].reasons == ["no citation"]


def test_out_of_range_citation_is_unsupported():
    assert not check_answer("Logbestanden blijven bewaard [7].", [PASSAGE])[0].supported


def test_similarity_threshold_uses_the_embedder():
    embed = lambda texts: np.tile([1.0, 0.0], (len(texts), 1))  # noqa: E731
    check = check_claim(
        "De aanbieder moet logbestanden bewaren", [PASSAGE], Thresholds(min_similarity=2.0), embed
    )
    assert any("similarity" in reason for reason in check.reasons)
