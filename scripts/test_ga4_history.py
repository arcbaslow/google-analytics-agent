import json
from unittest.mock import Mock

import ga4_admin as admin
import ga4_mcp
import pytest
from google.analytics.admin_v1alpha import types as alpha
from google.analytics.admin_v1beta import AnalyticsAdminServiceClient, types
from google.analytics.admin_v1beta.services.analytics_admin_service.pagers import (
    SearchChangeHistoryEventsPager,
)


def test_history_real_pager_scoped_dates_scrubbing_and_no_resource_snapshots(monkeypatch):
    client = Mock(spec=AnalyticsAdminServiceClient)
    factory = Mock(return_value=client)
    monkeypatch.setattr(admin, "_get_admin_client", factory)
    later = Mock(return_value=types.SearchChangeHistoryEventsResponse())

    def search_change_history_events(request, retry, timeout):
        assert request.property == "properties/123" and request.account == "accounts/456"
        assert request._pb.latest_change_time.nanos == 999999999
        return SearchChangeHistoryEventsPager(
            method=later,
            request=request,
            retry=retry,
            timeout=timeout,
            response=types.SearchChangeHistoryEventsResponse(
                next_page_token="page2",
                change_history_events=[
                    {
                        "id": "synthetic",
                        "user_actor_email": "person@example.com",
                        "actor_type": "USER",
                        "changes": [
                            {
                                "resource": "properties/123",
                                "action": "UPDATED",
                                "resource_after_change": {
                                    "property": {"display_name": "private snapshot"}
                                },
                            }
                        ],
                    }
                ],
            ),
        )

    client.search_change_history_events.side_effect = search_change_history_events
    out = ga4_mcp.change_history("456", "123", "2026-09-01", "2026-09-02")
    factory.assert_called_once_with(write=True)
    assert out["complete"] and out["time_zone"] == "UTC"
    assert out["events"][0]["changes"] == [{"resource": "properties/123", "action": "UPDATED"}]
    assert "person@example.com" not in str(out) and "private snapshot" not in str(out)
    assert later.call_count == 1 and later.call_args.kwargs["retry"] is None


def test_annotations_real_request_and_optional_support(monkeypatch):
    if not hasattr(alpha, "ListReportingDataAnnotationsRequest"):
        pytest.skip("optional annotations client")
    client = Mock()
    monkeypatch.setattr(admin, "_get_admin_alpha_client", lambda: client)
    client.list_reporting_data_annotations.return_value = [
        alpha.ReportingDataAnnotation(
            title="person@example.com", annotation_date={"year": 2026, "month": 9, "day": 1}
        )
    ]
    out = ga4_mcp.reporting_annotations("123", "2026-09-01", "2026-09-02")
    req = client.list_reporting_data_annotations.call_args.kwargs["request"]
    assert isinstance(req, alpha.ListReportingDataAnnotationsRequest)
    assert req.filter == 'is_annotation_in_range("2026-09-01", "2026-09-02") = true'
    assert out["complete"] and "person@example.com" not in str(out)


def test_missing_annotations_do_not_authenticate(monkeypatch):
    monkeypatch.delattr(alpha, "ListReportingDataAnnotationsRequest", raising=False)
    factory = Mock()
    monkeypatch.setattr(admin, "_get_admin_alpha_client", factory)
    assert admin.list_annotations("123", "2026-09-01", "2026-09-02")["status"] == "unsupported"
    factory.assert_not_called()


@pytest.mark.parametrize(
    "account,property_id,start,end",
    [
        ("bad", "123", "2026-09-01", "2026-09-02"),
        ("456", None, "2026-09-01", "2026-09-02"),
        ("456", "123", None, None),
        ("456", "123", "2026-09-02", "2026-09-01"),
        ("456", "123", "2024-01-01", "2026-09-02"),
    ],
)
def test_history_validation(account, property_id, start, end):
    with pytest.raises(ValueError):
        admin.search_change_history(account, property_id, start, end)


def test_cli_history_dispatch(monkeypatch, capsys):
    fn = Mock(return_value={"events": [], "complete": True})
    monkeypatch.setattr(admin, "search_change_history", fn)
    monkeypatch.setattr(
        "sys.argv",
        [
            "admin",
            "--change-history",
            "--property",
            "123",
            "--account",
            "456",
            "--start-date",
            "2026-09-01",
            "--end-date",
            "2026-09-02",
        ],
    )
    assert admin.main() == 0
    assert json.loads(capsys.readouterr().out)["complete"]
    fn.assert_called_once_with("456", "123", "2026-09-01", "2026-09-02")
