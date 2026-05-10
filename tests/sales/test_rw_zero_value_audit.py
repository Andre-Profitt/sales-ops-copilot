import pandas as pd

from scripts.sales.rw_zero_value_audit import audit_opportunity_zero_values


def _base_rows() -> list[dict]:
    return [
        {
            "opp_id": "r1",
            "motion_type": "Renewal",
            "is_closed": False,
            "is_won": False,
            "lead_source": "",
            "arr_org_ccy": None,
            "acv_org_ccy": 2_000_000.0,
            "saas_acv_org_ccy": 100_000.0,
            "axioma_order_inflow_org_ccy": 0.0,
            "ps_recurring_acv_org_ccy": 0.0,
        },
        {
            "opp_id": "l1",
            "motion_type": "Land",
            "is_closed": False,
            "is_won": False,
            "lead_source": "Partner referral",
            "arr_org_ccy": 1_500_000.0,
            "acv_org_ccy": None,
            "saas_acv_org_ccy": 500_000.0,
            "axioma_order_inflow_org_ccy": 250_000.0,
            "ps_recurring_acv_org_ccy": 75_000.0,
        },
        {
            "opp_id": "e1",
            "motion_type": "Expand",
            "is_closed": False,
            "is_won": False,
            "lead_source": "Direct",
            "arr_org_ccy": 750_000.0,
            "acv_org_ccy": None,
            "saas_acv_org_ccy": 125_000.0,
            "axioma_order_inflow_org_ccy": 100_000.0,
            "ps_recurring_acv_org_ccy": 50_000.0,
        },
    ]


def test_zero_value_audit_passes_nonzero_source_metrics():
    result = audit_opportunity_zero_values(pd.DataFrame(_base_rows()))

    assert result["summary"]["opportunity_rows"] == 3
    assert result["summary"]["severity_counts"]["high"] == 0


def test_zero_value_audit_flags_blank_populated_cohort():
    rows = _base_rows()
    rows[0]["acv_org_ccy"] = None

    result = audit_opportunity_zero_values(pd.DataFrame(rows))
    findings = {finding["measure"]: finding for finding in result["findings"]}

    assert findings["Total Open Renewal ACV"]["finding_id"] == "blank_source_field"
    assert findings["Total Open Renewal ACV"]["severity"] == "high"


def test_zero_value_audit_flags_empty_growth_mix_cohort():
    rows = [row for row in _base_rows() if row["motion_type"] == "Renewal"]

    result = audit_opportunity_zero_values(pd.DataFrame(rows))
    findings = {finding["measure"]: finding for finding in result["findings"]}

    assert findings["Open Land ARR"]["finding_id"] == "empty_source_cohort"
    assert findings["Open Land ARR"]["severity"] == "medium"
