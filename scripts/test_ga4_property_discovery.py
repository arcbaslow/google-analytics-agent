from unittest.mock import Mock

import ga4_auth
import pytest
from ga4_transport import ReadBudgetExceeded, read_budget
from google.analytics import admin_v1beta
from google.analytics.admin_v1beta.services.analytics_admin_service.pagers import (
    ListAccountSummariesPager,
)
from google.analytics.admin_v1beta.types import (
    ListAccountSummariesRequest,
    ListAccountSummariesResponse,
)
from google.api_core.exceptions import ResourceExhausted


def test_property_discovery_bounds_all_sdk_pages_and_scrubs_names(monkeypatch):
    monkeypatch.setattr(ga4_auth, "get_credentials", lambda **k: object())
    client = Mock(spec=admin_v1beta.AnalyticsAdminServiceClient)
    monkeypatch.setattr(admin_v1beta, "AnalyticsAdminServiceClient", Mock(return_value=client))
    second = Mock(
        return_value=ListAccountSummariesResponse(
            account_summaries=[
                {
                    "display_name": "person@example.com",
                    "property_summaries": [
                        {"property": "properties/123", "display_name": "Property"}
                    ],
                }
            ]
        )
    )

    def list_account_summaries(retry, timeout):
        return ListAccountSummariesPager(
            method=second,
            request=ListAccountSummariesRequest(),
            response=ListAccountSummariesResponse(next_page_token="next"),
            retry=retry,
            timeout=timeout,
        )

    client.list_account_summaries.side_effect = list_account_summaries
    with read_budget(1), pytest.raises(ReadBudgetExceeded):
        ga4_auth.list_properties()
    second.assert_not_called()
    with read_budget(2):
        out = ga4_auth.list_properties()
    assert out[0]["property_id"] == "123" and "person@example.com" not in str(out)
    assert second.call_args.kwargs["retry"] is None and second.call_args.kwargs["timeout"] == 30
    client.list_account_summaries.reset_mock(side_effect=True)
    client.list_account_summaries.side_effect = ResourceExhausted("quota")
    with pytest.raises(ResourceExhausted):
        ga4_auth.list_properties()
    client.list_account_summaries.assert_called_once()
