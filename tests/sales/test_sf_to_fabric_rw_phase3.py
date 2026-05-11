from __future__ import annotations

import pandas as pd

from scripts.sales.sf_to_fabric_rw_phase3 import transform


def test_forecast_transition_transform_excludes_omitted_before_ranking_and_lag(tmp_path):
    (tmp_path / "forecast_ofh.csv").write_text(
        "\n".join(
            [
                "OpportunityId,Field,OldValue,NewValue,CreatedDate",
                "opp-1,ForecastCategoryName,Pipeline,Omitted,2026-01-01T00:00:00Z",
                "opp-1,ForecastCategoryName,Omitted,Commit,2026-01-02T00:00:00Z",
                "opp-1,ForecastCategoryName,Commit,Pipeline,2026-01-05T00:00:00Z",
                "opp-1,ForecastCategoryName,Pipeline,Best Case,2026-01-07T00:00:00Z",
                "opp-2,ForecastCategoryName,Best Case,Closed,2026-02-01T00:00:00Z",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    df = transform(tmp_path)

    assert not df["from_category"].eq("Omitted").any()
    assert not df["to_category"].eq("Omitted").any()
    assert df[["opp_id", "from_category", "to_category", "direction"]].to_dict(
        "records"
    ) == [
        {
            "opp_id": "opp-1",
            "from_category": "Commit",
            "to_category": "Pipeline",
            "direction": "slip",
        },
        {
            "opp_id": "opp-1",
            "from_category": "Pipeline",
            "to_category": "Best Case",
            "direction": "upgrade",
        },
        {
            "opp_id": "opp-2",
            "from_category": "Best Case",
            "to_category": "Closed",
            "direction": "upgrade",
        },
    ]
    first_kept = df[df["opp_id"].eq("opp-1")].iloc[0]
    assert pd.isna(first_kept["prior_transition_at"])
