def test_salesmanager_report_loads(salesmanager_report):
    assert "sections" in salesmanager_report
    assert isinstance(salesmanager_report["sections"], list)


def test_empty_report_shape(empty_report):
    assert len(empty_report["sections"]) == 1
    assert empty_report["sections"][0]["visualContainers"] == []
