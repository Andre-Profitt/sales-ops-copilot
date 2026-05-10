from scripts.sales.rw_push_semantic_model import build_model_bim
from scripts.sales.rw_unit_policy import CURRENCY_M_FORMAT


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


def test_open_renewal_and_growth_measures_do_not_depend_on_closed_won_only():
    measures = _measure_map()

    assert measures["Total Open Renewal ACV"]["expression"] == (
        'CALCULATE ( SUM ( f_opportunity[acv_org_ccy] ), '
        'f_opportunity[is_closed] = FALSE(), f_opportunity[motion_type] = "Renewal" )'
    )
    assert measures["Total Renewal ACV Due"]["expression"] == (
        'CALCULATE ( SUM ( f_opportunity[acv_org_ccy] ), '
        'f_opportunity[motion_type] = "Renewal" )'
    )
    assert measures["Open Land ARR"]["expression"] == (
        'CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), '
        'f_opportunity[is_closed] = FALSE(), f_opportunity[motion_type] = "Land" )'
    )
    assert measures["Open Expand ARR"]["expression"] == (
        'CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), '
        'f_opportunity[is_closed] = FALSE(), f_opportunity[motion_type] = "Expand" )'
    )


def test_partner_arr_matches_partner_substrings_not_exact_only():
    expression = _measure_map()["Partner ARR"]["expression"]

    assert 'CONTAINSSTRING ( LOWER ( f_opportunity[lead_source] ), "partner" )' in expression
    assert 'f_opportunity[lead_source] = "Partner"' not in expression


def test_currency_measure_formats_are_locked_to_eur_m():
    measures = _measure_map()

    for name in [
        "Total Closed Won ARR",
        "Total Open Pipeline ARR",
        "Total Open Pipeline Value",
        "Total Open Renewal ACV",
        "Total Renewal ACV Won",
        "Stage Moves ARR 7d",
    ]:
        assert measures[name]["formatString"] == CURRENCY_M_FORMAT
