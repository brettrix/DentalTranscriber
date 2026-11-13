"""Every clinical attribute declares how Cs compares it (section 8)."""
from schemas.entities import ATTRIBUTE_MODELS, compare_table

VALID = {"exact", "normalized", "semantic", "excluded"}


def _check(table):
    for path, meta in table.items():
        assert meta.get("compare") in VALID, f"{path} has no comparison declaration"
        if meta["compare"] == "excluded":
            assert meta.get("reason"), f"{path} is excluded without a reason"
        if meta["compare"] == "normalized":
            assert meta.get("rule"), f"{path} is normalized without a rule"


def test_every_item_attribute_declares_comparison():
    for item_type, model in ATTRIBUTE_MODELS.items():
        table = compare_table("item", item_type)
        for name in model.model_fields:
            assert f"attributes.{name}" in table, f"{item_type}.{name} missing from compare table"
        _check(table)


def test_problem_and_relationship_fields_declare_comparison():
    _check(compare_table("problem"))
    _check(compare_table("relationship"))


def test_spec_examples_of_declarations():
    f = compare_table("item", "finding")
    assert f["attributes.lingering"]["compare"] == "exact"
    assert f["attributes.response"]["compare"] == "exact"
    assert f["attributes.duration_s"]["compare"] == "normalized"
    assert f["attributes.intensity"]["compare"] == "semantic"
    assert f["target.tooth"]["compare"] == "normalized"
    rx = compare_table("item", "prescription")
    for k in ("drug", "dose", "strength", "frequency_code", "duration_days"):
        assert rx[f"attributes.{k}"]["compare"] == "normalized"
    assert rx["attributes.original_wording"]["compare"] == "excluded"
    assert compare_table("item", "decision")["attributes.decision"]["compare"] == "exact"
    assert compare_table("problem")["complaint_text"]["compare"] == "semantic"
