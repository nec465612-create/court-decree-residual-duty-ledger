import hashlib
import json

import pytest


CONTRACT = "contracts/court_decree_residual_duty_ledger.py"
DECREE_URL = "https://www.justice.gov/crt/case-document/united-states-v-city-newark-consent-decree"
ORDER_URL = "https://www.justice.gov/crt/special-litigation-section-case-summaries"
DECREE_BODY = (
    "Case 2:16-cv-01731-MCA-MAH Document 5 Filed 05/05/16\n"
    "Paragraph 44 requires first-line-supervisor review. Paragraph 225 bounds the decree."
)
ORDER_BODY = (
    "Case 2:16-cv-01731-MCA-MAH Document 360 Filed 05/17/24 [PROPOSED] ORDER GRANTING "
    "the parties' joint motion for partial termination. IT IS ORDERED that the motion is granted. "
    "Paragraphs 5-12, 14-19, 21-28, 43, 55-62, 103-104 and 105-110 are terminated. "
    "Provisions not described in the termination subsection remain intact and monitored."
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _assessment(granted=True, ranges="5-12|14-19|21-28|43-43|55-62|103-104|105-110"):
    return {
        "case_match": True,
        "decree_match": True,
        "order_identity_match": True,
        "granted": granted,
        "terminated_ranges": ranges,
        "residual_clause_present": True,
        "evidence_state": "VERIFIED",
    }


@pytest.fixture(autouse=True)
def direct_runtime_guards(direct_vm):
    direct_vm.check_pickling = True
    direct_vm.strict_mocks = True


def _deploy_and_register(direct_deploy, direct_vm):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = contract.owner
    contract.register_decree(
        "newark-2016", "U.S. District Court", "2:16-cv-01731-MCA-MAH", "ECF-5",
        DECREE_URL, "2016-05-05-pdf", _sha256(DECREE_BODY), 225,
    )
    contract.seal_decree("newark-2016")
    contract.register_order(
        "newark-2016", "partial-termination-2024", "Document 360", ORDER_URL,
        "2024-05-17-pdf", _sha256(ORDER_BODY), "2024-05-17",
        "105-110|43-43|5-12|55-62|14-19|21-28|103-104",
    )
    contract.seal_order("newark-2016", "partial-termination-2024")
    return contract


def _mock_assessment(direct_vm, result=None):
    direct_vm.mock_web(r"justice\.gov/crt/case-document/united-states-v-city-newark-consent-decree", {"status": 200, "body": DECREE_BODY})
    direct_vm.mock_web(r"justice\.gov/crt/special-litigation-section-case-summaries", {"status": 200, "body": ORDER_BODY})
    direct_vm.mock_llm(
        r"bounded court-order modification record",
        json.dumps(json.dumps(result or _assessment())),
    )


def test_final_order_binds_terminated_and_surviving_paragraphs(
    direct_vm, direct_deploy
):
    contract = _deploy_and_register(direct_deploy, direct_vm)
    _mock_assessment(direct_vm)
    contract.assess_order("newark-2016", "partial-termination-2024")
    contract.review_paragraph("newark-2016", "partial-termination-2024", 43)
    contract.review_paragraph("newark-2016", "partial-termination-2024", 44)

    terminated = json.loads(contract.read_residual_duty("newark-2016", "partial-termination-2024", 43))
    survives = json.loads(contract.read_residual_duty("newark-2016", "partial-termination-2024", 44))
    assert terminated["result"] == "TERMINATED"
    assert survives["result"] == "SURVIVES_THIS_ORDER"
    assert terminated["order_state"] == "ASSESSED_FINAL"
    assert terminated["paragraph_id"] == 43


def test_paragraph_review_requires_completed_assessment(direct_vm, direct_deploy):
    contract = _deploy_and_register(direct_deploy, direct_vm)
    with direct_vm.expect_revert("order must be assessed before paragraph review"):
        contract.review_paragraph("newark-2016", "partial-termination-2024", 43)
    _mock_assessment(direct_vm)
    contract.assess_order("newark-2016", "partial-termination-2024")
    contract.review_paragraph("newark-2016", "partial-termination-2024", 43)
    assert json.loads(contract.get_review("newark-2016", "partial-termination-2024", 43))["state"] == "TERMINATED"


def test_range_canonicalization_and_order_identity_are_stored(direct_vm, direct_deploy):
    contract = _deploy_and_register(direct_deploy, direct_vm)
    _mock_assessment(direct_vm)
    contract.assess_order("newark-2016", "partial-termination-2024")
    order = json.loads(contract.get_order("newark-2016", "partial-termination-2024"))
    assert order["terminated_ranges"] == "5-12|14-19|21-28|43-43|55-62|103-104|105-110"
    assert order["state"] == "ASSESSED_FINAL"
    assert order["assessed_version"] == 1
    assert order["assessed_source_digest"] == hashlib.sha256(
        (_sha256(DECREE_BODY) + "|" + _sha256(ORDER_BODY)).encode("utf-8")
    ).hexdigest()


def test_motion_or_ungranted_order_is_not_final(direct_vm, direct_deploy):
    contract = _deploy_and_register(direct_deploy, direct_vm)
    _mock_assessment(direct_vm, _assessment(granted=False))
    contract.assess_order("newark-2016", "partial-termination-2024")
    contract.review_paragraph("newark-2016", "partial-termination-2024", 43)
    assert json.loads(contract.get_order("newark-2016", "partial-termination-2024"))["state"] == "NOT_FINAL"
    assert json.loads(contract.get_review("newark-2016", "partial-termination-2024", 43))["state"] == "NOT_FINAL"


def test_unresolved_evidence_never_creates_favorable_state(direct_vm, direct_deploy):
    contract = _deploy_and_register(direct_deploy, direct_vm)
    _mock_assessment(direct_vm, {
        **_assessment(),
        "evidence_state": "AMBIGUOUS",
    })
    contract.assess_order("newark-2016", "partial-termination-2024")
    contract.review_paragraph("newark-2016", "partial-termination-2024", 43)
    assert json.loads(contract.get_order("newark-2016", "partial-termination-2024"))["state"] == "UNRESOLVED"
    assert json.loads(contract.get_review("newark-2016", "partial-termination-2024", 43))["state"] == "UNRESOLVED"


def test_identity_or_residual_mismatch_is_unresolved(direct_vm, direct_deploy):
    contract = _deploy_and_register(direct_deploy, direct_vm)
    _mock_assessment(direct_vm, {
        **_assessment(),
        "case_match": False,
        "residual_clause_present": False,
    })
    contract.assess_order("newark-2016", "partial-termination-2024")
    contract.review_paragraph("newark-2016", "partial-termination-2024", 43)
    order = json.loads(contract.get_order("newark-2016", "partial-termination-2024"))
    assert order["state"] == "UNRESOLVED"
    assert json.loads(contract.get_review("newark-2016", "partial-termination-2024", 43))["state"] == "UNRESOLVED"


def test_source_drift_and_range_drift_revert_without_assessment(direct_vm, direct_deploy):
    contract = _deploy_and_register(direct_deploy, direct_vm)
    direct_vm.mock_web(r"justice\.gov/crt/case-document/united-states-v-city-newark-consent-decree", {"status": 200, "body": DECREE_BODY + " changed"})
    direct_vm.mock_web(r"justice\.gov/crt/special-litigation-section-case-summaries", {"status": 200, "body": ORDER_BODY})
    with direct_vm.expect_revert("decree source hash mismatch"):
        contract.assess_order("newark-2016", "partial-termination-2024")
    assert json.loads(contract.get_order("newark-2016", "partial-termination-2024"))["state"] == "SEALED"

    direct_vm.clear_mocks()
    _mock_assessment(direct_vm, _assessment(ranges="5-13"))
    with direct_vm.expect_revert("range extraction mismatch"):
        contract.assess_order("newark-2016", "partial-termination-2024")
    assert json.loads(contract.get_order("newark-2016", "partial-termination-2024"))["state"] == "SEALED"


def test_validator_disagreement_is_rejected(direct_vm, direct_deploy):
    contract = _deploy_and_register(direct_deploy, direct_vm)
    _mock_assessment(direct_vm)
    contract.assess_order("newark-2016", "partial-termination-2024")
    direct_vm.clear_mocks()
    _mock_assessment(direct_vm, _assessment(ranges="5-13"))
    assert direct_vm.run_validator() is False


def test_supersession_is_append_only_and_successor_is_distinct(direct_vm, direct_deploy):
    contract = _deploy_and_register(direct_deploy, direct_vm)
    direct_vm.sender = contract.owner
    contract.register_order(
        "newark-2016", "successor-order", "ECF-9", ORDER_URL, "2025-01-01",
        _sha256(ORDER_BODY), "2025-01-01", "43-43",
    )
    contract.seal_order("newark-2016", "successor-order")
    contract.supersede_order("newark-2016", "partial-termination-2024", "successor-order")
    old_order = json.loads(contract.get_order("newark-2016", "partial-termination-2024"))
    successor = json.loads(contract.get_order("newark-2016", "successor-order"))
    assert old_order["state"] == "SUPERSEDED"
    assert old_order["superseded_by"] == "successor-order"
    assert successor["state"] == "SEALED"


def test_validation_and_authorization_fail_closed(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("owner only"):
        contract.register_decree(
            "bad", "Court", "2:16-cv-01731-MCA-MAH", "ECF-5", DECREE_URL,
            "rev", _sha256(DECREE_BODY), 225,
        )
    direct_vm.sender = contract.owner
    contract.register_decree(
        "bad", "Court", "2:16-cv-01731-MCA-MAH", "ECF-5", DECREE_URL,
        "rev", _sha256(DECREE_BODY), 225,
    )
    contract.seal_decree("bad")
    with direct_vm.expect_revert("terminated_ranges overlap or are not disjoint"):
        contract.register_order(
            "bad", "overlap", "Document 360", ORDER_URL, "rev", _sha256(ORDER_BODY),
            "2024-05-17", "5-12|10-20",
        )
    with direct_vm.expect_revert("source_url host is not allowlisted"):
        contract.register_order(
            "bad", "wrong-host", "Document 360", "https://example.com/order.pdf", "rev",
            _sha256(ORDER_BODY), "2024-05-17", "5-12",
        )


def test_paragraph_outside_bounded_universe_is_rejected(direct_vm, direct_deploy):
    contract = _deploy_and_register(direct_deploy, direct_vm)
    with direct_vm.expect_revert("paragraph outside decree universe"):
        contract.review_paragraph("newark-2016", "partial-termination-2024", 226)


def test_identifier_whitespace_uses_one_canonical_storage_key(direct_vm, direct_deploy):
    contract = _deploy_and_register(direct_deploy, direct_vm)
    _mock_assessment(direct_vm)
    contract.assess_order(" newark-2016 ", " partial-termination-2024 ")
    contract.review_paragraph(" newark-2016 ", " partial-termination-2024 ", 43)
    result = json.loads(
        contract.read_residual_duty("newark-2016", "partial-termination-2024", 43)
    )
    assert result["result"] == "TERMINATED"


def test_dict_http_status_is_required_and_must_be_200(direct_vm, direct_deploy):
    contract = _deploy_and_register(direct_deploy, direct_vm)
    for response in (
        {"status": 404, "body": DECREE_BODY},
        {"status": 500, "body": DECREE_BODY},
        {"response": {"body": DECREE_BODY}},
    ):
        direct_vm.clear_mocks()
        direct_vm.mock_web(r"justice\.gov/crt/case-document/united-states-v-city-newark-consent-decree", response)
        with direct_vm.expect_revert():
            contract.assess_order("newark-2016", "partial-termination-2024")


def test_whitespace_only_identifier_is_rejected(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = contract.owner
    with direct_vm.expect_revert("decree_id has invalid length"):
        contract.register_decree(
            "   ", "Court", "2:16-cv-01731-MCA-MAH", "ECF-5", DECREE_URL,
            "rev", _sha256(DECREE_BODY), 225,
        )


def test_document_size_ceiling_accepts_twelve_megabyte_source(direct_vm, direct_deploy):
    large_body = DECREE_BODY + "x" * (12 * 1024 * 1024 - len(DECREE_BODY))
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = contract.owner
    contract.register_decree(
        "large-source", "Court", "2:16-cv-01731-MCA-MAH", "ECF-5", DECREE_URL,
        "large", _sha256(large_body), 225,
    )
    contract.seal_decree("large-source")
    contract.register_order(
        "large-source", "large-order", "Document 360", ORDER_URL, "large",
        _sha256(ORDER_BODY), "2024-05-17", "43-43",
    )
    contract.seal_order("large-source", "large-order")
    direct_vm.mock_web(r"justice\.gov/crt/case-document/united-states-v-city-newark-consent-decree", {"status": 200, "body": large_body})
    direct_vm.mock_web(r"justice\.gov/crt/special-litigation-section-case-summaries", {"status": 200, "body": ORDER_BODY})
    direct_vm.mock_llm(
        r"bounded court-order modification record",
        json.dumps(json.dumps(_assessment(ranges="43-43"))),
    )
    contract.assess_order("large-source", "large-order")
    assert json.loads(contract.get_order("large-source", "large-order"))["state"] == "ASSESSED_FINAL"
