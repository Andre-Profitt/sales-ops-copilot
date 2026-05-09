import json
import zipfile

from scripts.sales.rw_zebra_template_miner import (
    iter_pbix_layouts,
    mine_layouts,
    sanitized_object_groups,
)


def _write_fake_pbix(path, layout):
    with zipfile.ZipFile(path, "w") as pbix:
        pbix.writestr("Report/Layout", json.dumps(layout).encode("utf-16-le"))


def test_sanitized_object_groups_drops_license_settings():
    groups = sanitized_object_groups(
        {
            "objects": {
                "licenseSettings": [
                    {
                        "properties": {
                            "licenseKey": {
                                "expr": {"Literal": {"Value": "'secret'"}},
                            }
                        }
                    }
                ],
                "chartSettings": [{"properties": {"showGrandTotal": True}}],
            }
        }
    )

    assert "licenseSettings" not in groups
    assert groups == {"chartSettings": ["showGrandTotal"]}


def test_mine_layouts_reads_nested_pbix_and_emits_graph(tmp_path):
    layout = {
        "sections": [
            {
                "displayName": "Home",
                "visualContainers": [
                    {
                        "config": json.dumps(
                            {
                                "layouts": [
                                    {
                                        "position": {
                                            "x": 1,
                                            "y": 2,
                                            "width": 300,
                                            "height": 200,
                                        }
                                    }
                                ],
                                "singleVisual": {
                                    "visualType": (
                                        "ZebraBITables98F88148E5424E949E69864664EE1860"
                                    ),
                                    "projections": {
                                        "Category": [
                                            {
                                                "queryRef": "Customer.Region",
                                                "active": True,
                                            }
                                        ],
                                        "Values": [{"queryRef": "Data.AC"}],
                                    },
                                    "objects": {
                                        "licenseSettings": [
                                            {"properties": {"licenseKey": "secret"}}
                                        ],
                                        "chartSettings": [
                                            {"properties": {"showGrandTotal": True}}
                                        ],
                                    },
                                },
                            }
                        )
                    }
                ],
            }
        ]
    }
    pbix_path = tmp_path / "sample.pbix"
    _write_fake_pbix(pbix_path, layout)
    archive = tmp_path / "sales-funnel-power-bi-template__sample.zip"
    with zipfile.ZipFile(archive, "w") as outer:
        outer.write(pbix_path, "sample.pbix")
    pbix_path.unlink()

    layouts = iter_pbix_layouts(tmp_path)
    outputs = mine_layouts(layouts)

    assert len(layouts) == 1
    assert outputs["template_summary"][0]["zebra_visuals"] == 1
    assert outputs["visual_inventory"][0]["roles_json"] == (
        '{"Category": ["Customer.Region"], "Values": ["Data.AC"]}'
    )
    assert outputs["zebra_visual_patterns"][0]["object_groups"] == {
        "chartSettings": ["showGrandTotal"]
    }
    assert any(edge["relationship"] == "USES_FIELD" for edge in outputs["graph_edges"])
