from src.fieldops.inneros_adapter import read_inneros_context_snapshot


def test_inneros_adapter_is_read_only_and_reports_roots(tmp_path):
    status = tmp_path / "status.md"
    status.write_text("LIVE OK\n" * 200, encoding="utf-8")

    snapshot = read_inneros_context_snapshot(
        {
            "FIELDOPS_INNEROS_COORDINATION_ROOTS": f"{tmp_path}:/definitely/not/here",
            "FIELDOPS_INNEROS_MCP_PROFILE": "mcp-small",
            "FIELDOPS_INNEROS_MCP_URL": "https://mcp.example.test",
            "FIELDOPS_INNEROS_STATUS_PATH": str(status),
        }
    )

    assert snapshot["read_only"] is True
    assert snapshot["mutation_allowed"] is False
    assert snapshot["arbitrary_shell"] is False
    assert snapshot["arbitrary_network"] is False
    assert snapshot["mcp_profile"] == "mcp-small"
    assert snapshot["mcp_url_configured"] is True
    assert snapshot["roots"][0]["exists"] is True
    assert snapshot["roots"][1]["exists"] is False
    assert snapshot["status_path_exists"] is True
    assert len(snapshot["status_preview"]) <= 1200
