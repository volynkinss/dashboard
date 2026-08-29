from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_value = str(PROJECT_ROOT)
if project_root_value not in sys.path:
    sys.path.insert(0, project_root_value)

from scripts.seed_from_dashy import resolve_icon_fields


def test_resolve_icon_fields_supports_local_file_uri():
    icon_code, icon_url = resolve_icon_fields(
        "file:///app/data/icons/mail.png",
        item_url="https://example.internal",
        title="Mail",
    )

    assert icon_code == "MAIL"
    assert icon_url == "localfile:/app/data/icons/mail.png"


def test_resolve_icon_fields_supports_local_svg_file_uri():
    _, icon_url = resolve_icon_fields(
        "file:///app/data/icons/mail.svg",
        item_url="https://example.internal",
        title="Mail",
    )

    assert icon_url == "localfile:/app/data/icons/mail.svg"


def test_resolve_icon_fields_decodes_local_file_uri():
    _, icon_url = resolve_icon_fields(
        "file://localhost/app/data/icons/My%20Icon.png",
        item_url="https://example.internal",
        title="Example",
    )

    assert icon_url == "localfile:/app/data/icons/My Icon.png"


def test_resolve_icon_fields_rejects_remote_file_uri_hosts():
    _, icon_url = resolve_icon_fields(
        "file://fileserver/share/icon.png",
        item_url="https://example.internal",
        title="Example",
    )

    assert icon_url is None


def test_resolve_icon_fields_supports_existing_absolute_file_path(tmp_path):
    icon_file = tmp_path / "local-icon.png"
    icon_file.write_bytes(b"png")

    _, icon_url = resolve_icon_fields(
        str(icon_file),
        item_url="https://example.internal",
        title="Example",
    )

    assert icon_url == f"localfile:{icon_file}"
