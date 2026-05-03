from scripts.sales_director_row_filters import (
    filter_internal_sales_records,
    is_internal_account_name,
    is_internal_sales_record,
    is_test_opportunity_name,
)


def test_internal_account_name_filters_test_simcorp_and_sc_tokens() -> None:
    assert is_internal_account_name("SC Test Account")
    assert is_internal_account_name("SimCorp Demo Account")
    assert is_internal_account_name("North America SC")
    assert not is_internal_account_name("Scarborough Capital")
    assert not is_internal_account_name("Acme Securities")


def test_test_opportunity_name_filters_test_word_without_testing_false_positive() -> None:
    assert is_test_opportunity_name("Deal test")
    assert is_test_opportunity_name("APAC - Test")
    assert not is_test_opportunity_name("Continuous Testing module")


def test_nested_salesforce_records_are_filtered() -> None:
    rows = [
        {"Name": "Real expansion", "Account": {"Name": "Real Asset Manager"}},
        {"Name": "Real renewal", "Account": {"Name": "SimCorp Internal"}},
        {"Name": "Pipeline test", "Account": {"Name": "Real Bank"}},
        {"Opportunity": "Commercial deal", "AccountName": "SC Test Account"},
    ]
    assert filter_internal_sales_records(rows) == [rows[0]]


def test_is_internal_sales_record_checks_flat_table_rows() -> None:
    assert is_internal_sales_record({"Account": "Test Account", "Opportunity": "Real deal"})
    assert is_internal_sales_record({"Account": "Real Bank", "Opportunity": "Smoke test"})
    assert not is_internal_sales_record({"Account": "Real Bank", "Opportunity": "Expansion"})
