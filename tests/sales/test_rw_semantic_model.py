from scripts.sales.rw_push_semantic_model import build_model_bim


def _measure_map() -> dict[str, dict]:
    model = build_model_bim()["model"]
    return {
        measure["name"]: measure
        for table in model["tables"]
        for measure in table.get("measures", [])
    }


def test_arr_exception_measures_are_explicitly_land_expand_filtered():
    measures = _measure_map()
    land_expand = 'f_opportunity[motion_type] IN { "Land", "Expand" }'

    for name in [
        "At Risk Opps Count",
        "At Risk Opps ARR",
        "Watch Opps Count",
        "Watch Opps ARR",
        "Healthy Moves Count",
        "Healthy Moves ARR",
    ]:
        assert land_expand in measures[name]["expression"], name

    assert measures["Exception Opps Count"]["expression"] == (
        "[At Risk Opps Count] + [Watch Opps Count]"
    )
    assert measures["Exception ARR"]["expression"] == "[At Risk Opps ARR] + [Watch Opps ARR]"
