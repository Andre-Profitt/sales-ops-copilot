from scripts.sales.rw_push_semantic_model import build_model_bim
from scripts.sales.rw_unit_policy import CURRENCY_M_FORMAT


def _measure_map() -> dict[str, dict]:
    model = build_model_bim()["model"]
    return {
        measure["name"]: measure
        for table in model["tables"]
        for measure in table.get("measures", [])
    }


def _table_map() -> dict[str, dict]:
    model = build_model_bim()["model"]
    return {table["name"]: table for table in model["tables"]}


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


def test_active_asset_arr_measures_stay_out_of_renewal_acv_opportunity_proxy():
    measures = _measure_map()

    assert "f_asset_line_item[asset_arr_org_ccy]" in measures["Existing ARR Run Rate"]["expression"]
    assert "REMOVEFILTERS ( d_calendar )" in measures["Existing ARR Run Rate"]["expression"]
    assert 'f_asset_line_item[termination_risk] IN { "High", "Medium" }' in measures[
        "Business At Risk ARR"
    ]["expression"]
    assert "f_opportunity[acv_org_ccy]" not in measures["Business At Risk ARR"]["expression"]


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


def test_stage_order_semantics_are_in_model():
    tables = _table_map()
    opp_cols = {column["name"]: column for column in tables["f_opportunity"]["columns"]}
    transition_cols = {
        column["name"]: column for column in tables["f_stage_transition"]["columns"]
    }
    stage_cols = {column["name"]: column for column in tables["d_stage"]["columns"]}
    relationships = {
        rel["name"]: rel for rel in build_model_bim()["model"]["relationships"]
    }

    assert opp_cols["stage_name"]["sortByColumn"] == "stage_order"
    assert "stage_order" in opp_cols
    assert transition_cols["from_stage_name"]["sortByColumn"] == "from_stage_order"
    assert transition_cols["to_stage_name"]["sortByColumn"] == "to_stage_order"
    assert stage_cols["stage_name"]["sortByColumn"] == "stage_order"
    assert relationships["rel_opp_stage"] == {
        "name": "rel_opp_stage",
        "fromTable": "f_opportunity",
        "fromColumn": "stage_order",
        "toTable": "d_stage",
        "toColumn": "stage_order",
        "crossFilteringBehavior": "oneDirection",
    }
