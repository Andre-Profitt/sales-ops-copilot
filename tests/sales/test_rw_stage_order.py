from scripts.sales.rw_stage_order import parse_stage_label, stage_dimension_rows, stage_order_for_label


def test_stage_order_places_opt_out_after_contracting_and_before_won():
    assert stage_order_for_label("1 - Prospecting") == 1
    assert stage_order_for_label("6 - Contracting") == 6
    assert stage_order_for_label("0 - Opt-out") == 7
    assert stage_order_for_label("7 - Won") == 8


def test_stage_order_handles_actual_sales_ops_qc_stage_as_terminal():
    assert stage_order_for_label("7 - Sales Ops QC") == 8
    assert stage_order_for_label("8 - Won") == 8


def test_parse_stage_label_accepts_dash_or_dot_style():
    assert parse_stage_label("3 - Engagement") == (3, "Engagement")
    assert parse_stage_label("3. Engagement") == (3, "Engagement")


def test_stage_dimension_rows_are_unique_and_ordered():
    rows = stage_dimension_rows()

    assert [row["stage_order"] for row in rows] == [1, 2, 3, 4, 5, 6, 7, 8, 99]
    assert len({row["stage_order"] for row in rows}) == len(rows)
