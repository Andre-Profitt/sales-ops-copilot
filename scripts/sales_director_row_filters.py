"""Shared row filters for Sales Director deck/workbook outputs."""

from __future__ import annotations

import re
from typing import Any


_SC_ACCOUNT_RE = re.compile(r"(^|[^a-z0-9])sc([^a-z0-9]|$)", re.IGNORECASE)
_TEST_WORD_RE = re.compile(r"(^|[^a-z0-9])test([^a-z0-9]|$)", re.IGNORECASE)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def is_internal_account_name(value: Any) -> bool:
    """Return true for internal/test/seed account names that should not publish."""
    text = _text(value)
    lowered = text.casefold()
    if not lowered:
        return False
    if "test" in lowered or "simcorp" in lowered:
        return True
    return bool(_SC_ACCOUNT_RE.search(text))


def is_test_opportunity_name(value: Any) -> bool:
    # Match dummy/test opportunity labels without removing real commercial
    # service lines such as "Continuous Testing".
    return bool(_TEST_WORD_RE.search(_text(value)))


def _nested_value(record: dict[str, Any], parent: str, child: str) -> Any:
    value = record.get(parent)
    return value.get(child) if isinstance(value, dict) else None


def is_internal_sales_record(
    record: dict[str, Any],
    *,
    account_keys: tuple[str, ...] = ("Account", "AccountName", "account"),
    opportunity_keys: tuple[str, ...] = ("Name", "Opportunity", "OpportunityName", "name", "opportunity"),
) -> bool:
    account_values = [_nested_value(record, "Account", "Name")]
    account_values.extend(record.get(key) for key in account_keys)
    opportunity_values = [record.get(key) for key in opportunity_keys]
    return any(is_internal_account_name(value) for value in account_values) or any(
        is_test_opportunity_name(value) for value in opportunity_values
    )


def filter_internal_sales_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if not is_internal_sales_record(row)]
