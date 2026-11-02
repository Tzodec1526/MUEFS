import io
import os
import zipfile

import pytest

from app.config import settings
from app.utils.malware_scan import EICAR_TEST_SIGNATURE, scan_upload

PORT = os.getenv("MUEFS_TEST_CLAMAV_PORT")
pytestmark = pytest.mark.skipif(not PORT, reason="MUEFS_TEST_CLAMAV_PORT not configured")


@pytest.mark.parametrize("document", [
    "text", "upload_limit", "compressed_signature", "scan_limit", "nested_limit", "aggregate_limit",
])
async def test_real_daemon_requires_complete_scan(monkeypatch, document):
    monkeypatch.setattr(settings, "malware_scan_clamav_enabled", True)
    monkeypatch.setattr(settings, "clamav_host", "127.0.0.1")
    monkeypatch.setattr(settings, "clamav_port", int(PORT))
    monkeypatch.setattr(settings, "clamav_socket", "")
    if document in {"compressed_signature", "scan_limit", "nested_limit", "aggregate_limit"}:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
            if document == "aggregate_limit":
                for index in range(5):
                    package.writestr(
                        f"synthetic-{index}.txt", bytes([65 + index]) * (90 * 1024 * 1024),
                    )
            else:
                content = (EICAR_TEST_SIGNATURE if document == "compressed_signature"
                           else b"A" * (110 * 1024 * 1024))
                package.writestr("synthetic.txt", content)
        content = archive.getvalue()
        if document == "nested_limit":
            outer = io.BytesIO()
            with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_DEFLATED) as package:
                package.writestr("nested.zip", content)
            content = outer.getvalue()
        assert EICAR_TEST_SIGNATURE not in content
    else:
        content = b"Synthetic court document" if document == "text" else b"A" * (100 * 1024 * 1024)
    result = await scan_upload(content)
    assert result.engine == "clamav"
    assert result.is_clean == (document in {"text", "upload_limit"}), result
    if document in {"scan_limit", "nested_limit", "aggregate_limit"}:
        assert "exceeds screening limits" in result.reason, result
