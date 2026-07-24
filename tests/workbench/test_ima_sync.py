"""Tests for hermes.workbench.ima_sync (IMA knowledge base sync)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from hermes.workbench.ima_sync import (
    CONTENT_FORMAT_MARKDOWN,
    KB_PATH,
    MEDIA_TYPE_FILE,
    MEDIA_TYPE_NOTE,
    NOTES_PATH,
    ImaApiError,
    ImaClient,
    ImaConfigError,
    ImaKnowledgeBase,
    ImaNote,
    ImaSearchResult,
    ImaSyncResult,
    ImaSyncService,
)
from hermes.workbench.memory import MemoryService


# ---------------------------------------------------------------------------
# ImaClient tests
# ---------------------------------------------------------------------------


def test_ima_client_raises_config_error_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """ImaClient should raise ImaConfigError when credentials are missing."""
    monkeypatch.setattr(
        "hermes.workbench.ima_sync.get_settings",
        lambda: _FakeSettings(ima_openapi_clientid=None, ima_openapi_apikey=None),
    )
    client = ImaClient()
    with pytest.raises(ImaConfigError):
        client.list_knowledge_bases()


def test_ima_client_list_knowledge_bases(monkeypatch: pytest.MonkeyPatch) -> None:
    """list_knowledge_bases should parse API response correctly."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    fake_response = {
        "code": 0,
        "msg": "success",
        "data": {
            "info_list": [
                {
                    "kb_id": "abc123",
                    "kb_name": "测试知识库",
                    "content_count": "42",
                    "description": "test kb",
                    "base_type": "个人知识库",
                },
                {
                    "kb_id": "def456",
                    "kb_name": "AI知识库",
                    "content_count": "100",
                    "base_type": "共享知识库",
                },
            ],
            "is_end": True,
            "next_cursor": "",
        },
    }
    with patch.object(client, "_request", return_value=fake_response["data"]):
        kbs, is_end, cursor = client.list_knowledge_bases()
    assert len(kbs) == 2
    assert kbs[0].kb_id == "abc123"
    assert kbs[0].kb_name == "测试知识库"
    assert kbs[0].content_count == "42"
    assert is_end is True


def test_ima_client_search_knowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    """search_knowledge should parse search results correctly."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    fake_data = {
        "info_list": [
            {
                "title": "Python入门",
                "highlight_content": "Python是一门<b>简洁</b>的语言",
                "url": "https://example.com/1",
                "media_id": "m1",
            },
            {
                "title": "Java进阶",
                "highlight_content": "Java是企业级开发",
                "url": "https://example.com/2",
            },
        ],
        "is_end": True,
        "next_cursor": "",
    }
    with patch.object(client, "_request", return_value=fake_data):
        results, is_end, cursor = client.search_knowledge("Python", "kb1")
    assert len(results) == 2
    assert results[0].title == "Python入门"
    assert "简洁" in results[0].highlight_content
    assert results[0].url == "https://example.com/1"
    assert is_end is True


def test_ima_client_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """_request should raise ImaApiError when code != 0."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    # Mock urllib to return error response
    fake_error_response = {
        "code": 20004,
        "msg": "invalid credentials",
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(fake_error_response).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(ImaApiError) as exc_info:
            client.list_knowledge_bases()
    assert "20004" in str(exc_info.value)


# ---------------------------------------------------------------------------
# ImaClient: notes module (note/v1)
# ---------------------------------------------------------------------------


def test_ima_client_import_doc_uses_notes_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """import_doc should POST to /openapi/note/v1/import_doc with content_format."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    captured: dict[str, Any] = {}

    def fake_request(module_path: str, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        captured["module_path"] = module_path
        captured["endpoint"] = endpoint
        captured["body"] = body
        return {"doc_id": "n1"}

    with patch.object(client, "_request", side_effect=fake_request):
        result = client.import_doc(content="hello", title="My Note")
    assert captured["module_path"] == NOTES_PATH
    assert captured["endpoint"] == "import_doc"
    assert captured["body"]["content_format"] == CONTENT_FORMAT_MARKDOWN
    # Title should be prepended as H1 when not in content
    assert captured["body"]["content"].startswith("# My Note")
    assert "hello" in captured["body"]["content"]
    assert result == {"doc_id": "n1"}


def test_ima_client_import_doc_no_title_prepend(monkeypatch: pytest.MonkeyPatch) -> None:
    """import_doc should not prepend title if it is already in content."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    captured: dict[str, Any] = {}

    def fake_request(module_path: str, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        captured["body"] = body
        return {}

    content_with_title = "# Existing Title\n\nbody text"
    with patch.object(client, "_request", side_effect=fake_request):
        client.import_doc(content=content_with_title, title="Existing Title")
    assert captured["body"]["content"] == content_with_title


def test_ima_client_append_doc(monkeypatch: pytest.MonkeyPatch) -> None:
    """append_doc should POST to note/v1/append_doc with note_id and content."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    captured: dict[str, Any] = {}

    def fake_request(module_path: str, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        captured.update({"module_path": module_path, "endpoint": endpoint, "body": body})
        return {"note_id": "n123"}

    with patch.object(client, "_request", side_effect=fake_request):
        client.append_doc(note_id="n123", content="extra text")
    assert captured["module_path"] == NOTES_PATH
    assert captured["endpoint"] == "append_doc"
    assert captured["body"]["note_id"] == "n123"
    assert captured["body"]["content"] == "extra text"
    assert captured["body"]["content_format"] == CONTENT_FORMAT_MARKDOWN


def test_ima_client_search_note_book(monkeypatch: pytest.MonkeyPatch) -> None:
    """search_note_book should parse notes from nested `docs[].doc.basic_info`."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    # Live API returns each doc as {"doc": {"basic_info": {...}}}
    # and total_hit_num as a string.
    fake_data = {
        "docs": [
            {
                "doc": {
                    "basic_info": {
                        "docid": "n1",
                        "title": "Note One",
                        "summary": "summary 1",
                        "create_time": "1784905087866",
                        "modify_time": "1784905087866",
                        "folder_id": "f1",
                        "folder_name": "Folder1",
                    }
                }
            },
            {
                "doc": {
                    "basic_info": {
                        "docid": "n2",
                        "title": "Note Two",
                        "summary": "summary 2",
                    }
                }
            },
        ],
        "is_end": True,
        "total_hit_num": "2",  # string in live API
    }
    with patch.object(client, "_request", return_value=fake_data):
        notes, is_end, total = client.search_note_book("Note")
    assert len(notes) == 2
    assert isinstance(notes[0], ImaNote)
    assert notes[0].note_id == "n1"  # parsed from docid
    assert notes[0].title == "Note One"
    assert notes[0].summary == "summary 1"
    assert notes[0].folder_id == "f1"
    assert notes[0].folder_name == "Folder1"
    assert is_end is True
    assert total == 2  # parsed from string "2"
    assert isinstance(total, int)


def test_ima_client_list_note(monkeypatch: pytest.MonkeyPatch) -> None:
    """list_note should paginate notes using `note_book_list` response field."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    fake_data = {
        "note_book_list": [
            {
                "note_id": "n1",
                "title": "First",
                "summary": "first summary",
                "create_time": "1784905087866",
                "modify_time": "1784905087866",
                "note_ext_info": {"folder_id": "f1", "folder_name": "Folder1"},
            },
        ],
        "is_end": False,
    }
    captured: dict[str, Any] = {}
    with patch.object(
        client, "_request", side_effect=lambda mp, ep, body: (
            captured.update({"mp": mp, "ep": ep, "body": body}) or fake_data
        )
    ):
        notes, is_end, cursor = client.list_note(limit=10)
    assert captured["mp"] == NOTES_PATH
    assert captured["ep"] == "list_note"
    # Body uses lowercase `limit` but capitalized `Cursor` (verified live)
    assert captured["body"] == {"limit": 10, "Cursor": ""}
    assert len(notes) == 1
    assert notes[0].note_id == "n1"
    assert notes[0].title == "First"
    assert notes[0].folder_id == "f1"
    assert notes[0].folder_name == "Folder1"
    assert is_end is False


def test_ima_client_get_doc_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_doc_content should return raw data dict and use note_id field."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    fake_data = {"note_id": "n1", "content": "# Title\n\nbody", "title": "Title"}
    captured: dict[str, Any] = {}
    with patch.object(
        client, "_request", side_effect=lambda mp, ep, body: (captured.update({
            "mp": mp, "ep": ep, "body": body
        }) or fake_data)
    ):
        result = client.get_doc_content("n1")
    assert result == fake_data
    assert captured["mp"] == NOTES_PATH
    assert captured["ep"] == "get_doc_content"
    # Should use note_id (preferred over doc_id)
    assert captured["body"] == {"note_id": "n1"}


def test_ima_client_create_note_alias_delegates_to_import_doc(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """create_note (backward-compat) should delegate to import_doc and ignore kb_id."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    with patch.object(client, "import_doc", return_value={"ok": True}) as mock_import:
        result = client.create_note("kb-ignored", "Note Title", "body content")
    mock_import.assert_called_once_with(content="body content", title="Note Title")
    assert result == {"ok": True}


def test_ima_client_get_addable_knowledge_base_list(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_addable_knowledge_base_list should use wiki/v1 module path."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    captured: dict[str, Any] = {}

    def fake_request(mp: str, ep: str, body: dict[str, Any]) -> dict[str, Any]:
        captured.update({"mp": mp, "ep": ep, "body": body})
        return {
            "info_list": [{"kb_id": "k1", "kb_name": "Addable KB"}],
            "is_end": True,
            "next_cursor": "",
        }

    with patch.object(client, "_request", side_effect=fake_request):
        kbs, is_end, cursor = client.get_addable_knowledge_base_list(limit=5)
    assert captured["mp"] == KB_PATH
    assert captured["ep"] == "get_addable_knowledge_base_list"
    assert captured["body"] == {"cursor": "", "limit": 5}
    assert len(kbs) == 1
    assert kbs[0].kb_id == "k1"
    assert is_end is True


# ---------------------------------------------------------------------------
# ImaClient tests: knowledge-base module (import_urls / add_knowledge / upload)
# ---------------------------------------------------------------------------


def test_ima_client_import_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    """import_urls should POST to wiki/v1/import_urls with kb_id and urls list."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    captured: dict[str, Any] = {}

    def fake_request(mp: str, ep: str, body: dict[str, Any]) -> dict[str, Any]:
        captured.update({"mp": mp, "ep": ep, "body": body})
        return {"task_id": "t1"}

    with patch.object(client, "_request", side_effect=fake_request):
        result = client.import_urls("kb1", ["https://a.com", "https://b.com"])
    assert captured["mp"] == KB_PATH
    assert captured["ep"] == "import_urls"
    assert captured["body"] == {
        "knowledge_base_id": "kb1",
        "urls": ["https://a.com", "https://b.com"],
    }
    assert result == {"task_id": "t1"}


def test_ima_client_import_urls_with_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    """import_urls should include folder_id when provided."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    captured: dict[str, Any] = {}
    with patch.object(
        client, "_request",
        side_effect=lambda mp, ep, body: (captured.update({"body": body}) or {}),
    ):
        client.import_urls("kb1", ["https://a.com"], folder_id="folder1")
    assert captured["body"]["folder_id"] == "folder1"


def test_ima_client_import_urls_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """import_urls should raise ImaApiError when urls list is empty."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    with pytest.raises(ImaApiError):
        client.import_urls("kb1", [])


def test_ima_client_add_knowledge_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """add_knowledge should default to media_type=10 (file)."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    captured: dict[str, Any] = {}
    with patch.object(
        client, "_request",
        side_effect=lambda mp, ep, body: (captured.update({"mp": mp, "ep": ep, "body": body}) or {}),
    ):
        client.add_knowledge("kb1", "media1")
    assert captured["mp"] == KB_PATH
    assert captured["ep"] == "add_knowledge"
    assert captured["body"] == {
        "knowledge_base_id": "kb1",
        "media_id": "media1",
        "media_type": MEDIA_TYPE_FILE,
    }


def test_ima_client_add_knowledge_note(monkeypatch: pytest.MonkeyPatch) -> None:
    """add_knowledge should accept media_type=11 (note) for note association."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    captured: dict[str, Any] = {}
    with patch.object(
        client, "_request",
        side_effect=lambda mp, ep, body: (captured.update({"body": body}) or {}),
    ):
        client.add_knowledge("kb1", "note1", media_type=MEDIA_TYPE_NOTE, folder_id="f1")
    assert captured["body"]["media_type"] == MEDIA_TYPE_NOTE
    assert captured["body"]["folder_id"] == "f1"


def test_ima_client_create_media(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_media should derive file_ext from file_name when not provided."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    captured: dict[str, Any] = {}

    def fake_request(mp: str, ep: str, body: dict[str, Any]) -> dict[str, Any]:
        captured.update({"mp": mp, "ep": ep, "body": body})
        return {"media_id": "m1", "upload_url": "https://cos.example.com/put"}

    with patch.object(client, "_request", side_effect=fake_request):
        result = client.create_media(
            kb_id="kb1",
            file_name="report.pdf",
            file_size=1024,
            content_type="application/pdf",
        )
    assert captured["mp"] == KB_PATH
    assert captured["ep"] == "create_media"
    assert captured["body"]["file_ext"] == "pdf"
    assert captured["body"]["file_size"] == 1024
    assert result["media_id"] == "m1"
    assert "upload_url" in result


def test_ima_client_create_media_explicit_ext(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_media should use explicitly provided file_ext."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    captured: dict[str, Any] = {}
    with patch.object(
        client, "_request",
        side_effect=lambda mp, ep, body: (captured.update({"body": body}) or {}),
    ):
        client.create_media("kb1", "data.dat", 100, file_ext="bin")
    assert captured["body"]["file_ext"] == "bin"


def test_ima_client_upload_file_full_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """upload_file should run create_media → cos_put → add_knowledge."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    # Create a small test file
    test_file = tmp_path / "doc.pdf"
    test_file.write_bytes(b"%PDF-1.4 test content")

    call_log: list[tuple[str, ...]] = []

    def fake_create_media(kb_id: str, file_name: str, file_size: int,
                          content_type: str = "", file_ext: str = "") -> dict[str, Any]:
        call_log.append(("create_media", kb_id, file_name, file_size))
        return {"media_id": "m123", "upload_url": "https://cos.example.com/put"}

    def fake_add_knowledge(kb_id: str, media_id: str, media_type: int = 0,
                           folder_id: str = "") -> dict[str, Any]:
        call_log.append(("add_knowledge", kb_id, media_id, media_type))
        return {"ok": True}

    with patch.object(client, "create_media", side_effect=fake_create_media):
        with patch.object(client, "add_knowledge", side_effect=fake_add_knowledge):
            with patch.object(client, "_cos_put") as mock_cos:
                result = client.upload_file("kb1", test_file, content_type="application/pdf")

    assert call_log[0][0] == "create_media"
    assert call_log[0][3] == len(b"%PDF-1.4 test content")
    assert call_log[1][0] == "add_knowledge"
    assert call_log[1][3] == MEDIA_TYPE_FILE
    mock_cos.assert_called_once()
    # COS PUT should have received the file bytes
    cos_args, cos_kwargs = mock_cos.call_args
    assert cos_args[1] == b"%PDF-1.4 test content"
    assert result["media_id"] == "m123"
    assert result["file_name"] == "doc.pdf"
    assert result["add_knowledge"] == {"ok": True}


def test_ima_client_upload_file_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """upload_file should raise ImaApiError when file does not exist."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    with pytest.raises(ImaApiError):
        client.upload_file("kb1", tmp_path / "nonexistent.pdf")


def test_ima_client_upload_file_missing_upload_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """upload_file should raise ImaApiError when create_media omits upload_url."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    test_file = tmp_path / "doc.pdf"
    test_file.write_bytes(b"content")
    with patch.object(client, "create_media", return_value={"media_id": "m1"}):
        with pytest.raises(ImaApiError) as exc_info:
            client.upload_file("kb1", test_file)
    assert "upload_url" in str(exc_info.value).lower() or "media_id" in str(exc_info.value).lower()


def test_ima_client_cos_put_uses_put_method(monkeypatch: pytest.MonkeyPatch) -> None:
    """_cos_put should issue a PUT request with Content-Length header."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    captured: dict[str, Any] = {}
    mock_resp = MagicMock()
    mock_resp.read.return_value = b""
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    class FakeRequest:
        def __init__(self, url: str, data: bytes, method: str) -> None:
            captured["url"] = url
            captured["data"] = data
            captured["method"] = method
            self._headers: dict[str, str] = {}

        def add_header(self, key: str, value: str) -> None:
            captured.setdefault("headers", {})[key] = value

    with patch("urllib.request.Request", FakeRequest):
        with patch("urllib.request.urlopen", return_value=mock_resp):
            client._cos_put("https://cos.example.com/put", b"hello", content_type="text/plain")
    assert captured["method"] == "PUT"
    assert captured["data"] == b"hello"
    assert captured["headers"]["Content-Type"] == "text/plain"
    assert captured["headers"]["Content-Length"] == "5"


def test_ima_client_cos_put_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """_cos_put should raise ImaApiError on HTTP failure."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient()
    import urllib.error
    fake_err = urllib.error.HTTPError(
        url="https://cos.example.com/put",
        code=403,
        msg="Forbidden",
        hdrs=None,
        fp=None,
    )
    with patch("urllib.request.urlopen", side_effect=fake_err):
        with pytest.raises(ImaApiError) as exc_info:
            client._cos_put("https://cos.example.com/put", b"hello")
    assert "COS PUT failed" in str(exc_info.value)


# ---------------------------------------------------------------------------
# ImaSyncService tests
# ---------------------------------------------------------------------------


def test_sync_service_push_urls_records_episode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """push_urls should call import_urls and record an episode."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    memory = MemoryService(state_dir=tmp_path / "state")
    mock_client = MagicMock(spec=ImaClient)
    mock_client.import_urls.return_value = {"task_id": "t1"}
    svc = ImaSyncService(client=mock_client, memory=memory)
    result = svc.push_urls("kb1", ["https://a.com", "https://b.com"], folder_id="f1")
    assert result == {"task_id": "t1"}
    mock_client.import_urls.assert_called_once_with(
        "kb1", ["https://a.com", "https://b.com"], folder_id="f1"
    )
    episodes = memory.list_episodes(kind="ima_push_urls")
    assert len(episodes) == 1
    assert "2 url(s)" in episodes[0].summary
    assert episodes[0].details["count"] == 2


def test_sync_service_push_file_records_episode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """push_file should call upload_file and record an episode."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    memory = MemoryService(state_dir=tmp_path / "state")
    test_file = tmp_path / "report.pdf"
    test_file.write_bytes(b"pdf content")
    mock_client = MagicMock(spec=ImaClient)
    mock_client.upload_file.return_value = {
        "media_id": "m1",
        "kb_id": "kb1",
        "file_name": "report.pdf",
        "file_size": 11,
        "add_knowledge": {"ok": True},
    }
    svc = ImaSyncService(client=mock_client, memory=memory)
    result = svc.push_file("kb1", test_file, folder_id="f1")
    assert result["media_id"] == "m1"
    mock_client.upload_file.assert_called_once_with(
        "kb1", test_file, content_type=None, folder_id="f1"
    )
    episodes = memory.list_episodes(kind="ima_push_file")
    assert len(episodes) == 1
    assert "report.pdf" in episodes[0].summary
    assert episodes[0].details["file_size"] == 11


# ---------------------------------------------------------------------------
# ImaSyncService tests (original)
# ---------------------------------------------------------------------------


def test_sync_service_pull_records_episodes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """pull should record each result as an L2 episode."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    memory = MemoryService(state_dir=tmp_path / "state")
    mock_client = MagicMock(spec=ImaClient)
    mock_client.search_knowledge.return_value = (
        [
            ImaSearchResult(title="Result 1", highlight_content="content 1"),
            ImaSearchResult(title="Result 2", highlight_content="content 2"),
        ],
        True,
        "",
    )
    svc = ImaSyncService(client=mock_client, memory=memory)
    results = svc.pull("test query", "kb123")
    assert len(results) == 2
    episodes = memory.list_episodes(kind="ima_pull")
    assert len(episodes) == 2
    # Episodes are most-recent-first; check both exist
    summaries = [ep.summary for ep in episodes]
    assert any("[IMA] Result 1" in s for s in summaries)
    assert any("[IMA] Result 2" in s for s in summaries)


def test_sync_service_push_records_episode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """push should call create_note and record an episode."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    memory = MemoryService(state_dir=tmp_path / "state")
    mock_client = MagicMock(spec=ImaClient)
    mock_client.create_note.return_value = {"note_id": "n1"}
    svc = ImaSyncService(client=mock_client, memory=memory)
    result = svc.push("kb1", "Test Note", "content body")
    assert result == {"note_id": "n1"}
    mock_client.create_note.assert_called_once_with("kb1", "Test Note", "content body")
    episodes = memory.list_episodes(kind="ima_push")
    assert len(episodes) == 1
    assert "[IMA Push] Test Note" in episodes[0].summary


def test_sync_service_push_episodes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """push_episodes should push recent episodes to IMA."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    memory = MemoryService(state_dir=tmp_path / "state")
    # Record some episodes first
    from hermes.workbench.memory import make_episode
    memory.record_episode(make_episode("note", "Episode A", {"key": "val1"}))
    memory.record_episode(make_episode("note", "Episode B", {"key": "val2"}))
    mock_client = MagicMock(spec=ImaClient)
    mock_client.create_note.return_value = {"ok": True}
    svc = ImaSyncService(client=mock_client, memory=memory)
    result = svc.push_episodes("kb1", kind="note", limit=10)
    assert result.pushed == 2
    assert len(result.errors) == 0


def test_sync_service_sync_bidirectional(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync should pull from IMA and push episodes to IMA."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    memory = MemoryService(state_dir=tmp_path / "state")
    from hermes.workbench.memory import make_episode
    memory.record_episode(make_episode("note", "Existing Episode", {"data": "test"}))
    mock_client = MagicMock(spec=ImaClient)
    mock_client.search_knowledge.return_value = (
        [ImaSearchResult(title="Pulled Item", highlight_content="content")],
        True,
        "",
    )
    mock_client.create_note.return_value = {"ok": True}
    svc = ImaSyncService(client=mock_client, memory=memory)
    result = svc.sync("query", "kb1", push_kind="note")
    assert result.pulled == 1
    assert result.pushed == 1
    assert len(result.errors) == 0


def test_sync_service_sync_handles_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync should continue even if one direction fails."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    memory = MemoryService(state_dir=tmp_path / "state")
    mock_client = MagicMock(spec=ImaClient)
    mock_client.search_knowledge.side_effect = ImaApiError("search failed", 500)
    mock_client.create_note.return_value = {"ok": True}
    svc = ImaSyncService(client=mock_client, memory=memory)
    result = svc.sync("query", "kb1")
    assert result.pulled == 0
    assert len(result.errors) > 0
    assert "pull" in result.errors[0]


# ---------------------------------------------------------------------------
# Error mapping & retry mechanism tests
# ---------------------------------------------------------------------------


def test_ima_api_error_friendly_message_known_code() -> None:
    """friendly_message should return a Chinese hint for known error codes."""
    err = ImaApiError("invalid credentials", 20004)
    msg = err.friendly_message()
    assert "认证失败" in msg
    assert "20004" in msg  # raw message preserved in parens


def test_ima_api_error_friendly_message_unknown_code() -> None:
    """friendly_message should fall back to raw message for unknown codes."""
    err = ImaApiError("weird error", 99999)
    msg = err.friendly_message()
    assert "99999" in msg


def test_ima_is_retryable_rate_limit() -> None:
    """_is_retryable should return True for IMA rate-limit code 20006."""
    err = ImaApiError("rate limited", 20006)
    assert ImaClient._is_retryable(err) is True


def test_ima_is_retryable_http_500() -> None:
    """_is_retryable should return True for HTTP 500."""
    err = ImaApiError("HTTP 500", 500)
    assert ImaClient._is_retryable(err) is True


def test_ima_is_retryable_http_429() -> None:
    """_is_retryable should return True for HTTP 429 (Too Many Requests)."""
    err = ImaApiError("HTTP 429", 429)
    assert ImaClient._is_retryable(err) is True


def test_ima_is_retryable_not_retryable_for_auth_error() -> None:
    """_is_retryable should return False for auth errors (20004) — no point retrying."""
    err = ImaApiError("auth failed", 20004)
    assert ImaClient._is_retryable(err) is False


def test_ima_is_retryable_not_retryable_for_404() -> None:
    """_is_retryable should return False for HTTP 404 (Not Found)."""
    err = ImaApiError("HTTP 404", 404)
    assert ImaClient._is_retryable(err) is False


def test_ima_request_retries_on_rate_limit_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_request should retry on IMA code 20006 and succeed on a later attempt."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient(max_retries=3, backoff_base=0.0)  # no real sleep
    call_count = {"n": 0}

    def flaky_request_once(mp: str, ep: str, body: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise ImaApiError("rate limited", 20006)
        return {"ok": True}

    with patch.object(client, "_request_once", side_effect=flaky_request_once):
        result = client._request("wiki/v1", "search_knowledge_base", {})
    assert result == {"ok": True}
    assert call_count["n"] == 3  # failed twice, succeeded on 3rd


def test_ima_request_does_not_retry_on_auth_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_request should NOT retry on non-retryable errors (e.g. 20004 auth)."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient(max_retries=3, backoff_base=0.0)
    call_count = {"n": 0}

    def always_fail(mp: str, ep: str, body: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        raise ImaApiError("auth failed", 20004)

    with patch.object(client, "_request_once", side_effect=always_fail):
        with pytest.raises(ImaApiError):
            client._request("wiki/v1", "search_knowledge_base", {})
    assert call_count["n"] == 1  # no retries


def test_ima_request_retries_until_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_request should retry max_retries times then raise the last error."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient(max_retries=2, backoff_base=0.0)
    call_count = {"n": 0}

    def always_500(mp: str, ep: str, body: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        raise ImaApiError("HTTP 500", 500)

    with patch.object(client, "_request_once", side_effect=always_500):
        with pytest.raises(ImaApiError) as exc_info:
            client._request("wiki/v1", "search_knowledge_base", {})
    assert call_count["n"] == 2  # max_retries attempts
    assert exc_info.value.code == 500


def test_ima_cos_put_retries_on_500_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_cos_put should retry on HTTP 500 and succeed on a later attempt."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient(max_retries=3, backoff_base=0.0)
    call_count = {"n": 0}

    real_http_error = __import__("urllib.error", fromlist=["HTTPError"]).HTTPError

    def flaky_urlopen(req: Any, timeout: float = 0) -> Any:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise real_http_error(req.full_url, 500, "Server Error", None, None)
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=flaky_urlopen):
        client._cos_put("https://cos.example.com/put", b"hello")
    assert call_count["n"] == 3


def test_ima_cos_put_no_retry_on_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_cos_put should NOT retry on HTTP 403 (non-retryable)."""
    monkeypatch.setattr("hermes.workbench.ima_sync.get_settings", lambda: _FakeSettings())
    client = ImaClient(max_retries=3, backoff_base=0.0)
    call_count = {"n": 0}
    real_http_error = __import__("urllib.error", fromlist=["HTTPError"]).HTTPError

    def always_403(req: Any, timeout: float = 0) -> Any:
        call_count["n"] += 1
        raise real_http_error(req.full_url, 403, "Forbidden", None, None)

    with patch("urllib.request.urlopen", side_effect=always_403):
        with pytest.raises(ImaApiError) as exc_info:
            client._cos_put("https://cos.example.com/put", b"hello")
    assert call_count["n"] == 1
    assert exc_info.value.code == 403


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSettings:
    """Minimal settings fake for IMA config."""

    def __init__(
        self,
        ima_openapi_clientid: str | None = "test-client-id",
        ima_openapi_apikey: str | None = "test-api-key",
        ima_openapi_base_url: str = "https://ima.qq.com",
    ) -> None:
        self.ima_openapi_clientid = ima_openapi_clientid
        self.ima_openapi_apikey = ima_openapi_apikey
        self.ima_openapi_base_url = ima_openapi_base_url
