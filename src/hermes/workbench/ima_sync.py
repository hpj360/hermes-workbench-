"""IMA 知识库同步服务 (Tencent IMA OpenAPI).

Provides bidirectional sync between Hermes memory and IMA knowledge bases.

Authentication uses two custom HTTP headers:
    ima-openapi-clientid: <Client ID>
    ima-openapi-apikey:   <API Key>

All requests are POST + JSON, implemented with pure stdlib (urllib).

The IMA OpenAPI is split into two modules with distinct path prefixes:

knowledge-base module (/openapi/wiki/v1/):
    search_knowledge_base            — list/search knowledge bases
    search_knowledge                 — search content in a knowledge base
    get_knowledge_list               — browse folder contents
    get_addable_knowledge_base_list  — list addable knowledge bases
    import_urls                      — batch import web pages by URL
    add_knowledge                    — attach a note/file to a knowledge base
    create_media                     — step 1 of file upload: get COS credentials
    upload_file                      — full 3-step file upload flow

notes module (/openapi/note/v1/):
    import_doc        — create a new note (markdown content)
    append_doc        — append content to an existing note
    search_note_book  — search notes by title
    list_note         — list notes (returns note_book_list)
    get_doc_content   — fetch full content of a note

Field name caveats (verified against the live API on 2026-07-24):
    * list_note body uses lowercase `limit` but capitalized `Cursor`.
    * list_note response returns `note_book_list` (not `info_list`).
    * search_note_book response returns `docs` (not `info_list`).
    * append_doc / get_doc_content accept either `doc_id` or `note_id`.
    * Notes carry `note_id` (string); there is no separate `doc_id` field
      in list responses, so we expose it as `note_id` on ImaNote.

File upload flow (knowledge-base module):
    1. create_media  → returns COS pre-signed upload URL + media_id
    2. PUT file bytes to the COS URL (no IMA auth headers)
    3. add_knowledge with media_type=10 and the media_id
"""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hermes.config import get_settings
from hermes.workbench.memory import MemoryService, make_episode


# ---------------------------------------------------------------------------
# Module path constants
# ---------------------------------------------------------------------------

KB_PATH = "wiki/v1"        # knowledge-base module prefix
NOTES_PATH = "note/v1"     # notes module prefix

# Content format constants for notes module
CONTENT_FORMAT_MARKDOWN = 1
CONTENT_FORMAT_PLAINTEXT = 0

# Media type constants for add_knowledge (knowledge-base module)
MEDIA_TYPE_FILE = 10   # attach an uploaded file (via create_media)
MEDIA_TYPE_NOTE = 11   # attach an existing note


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ImaKnowledgeBase:
    """An IMA knowledge base entry."""

    kb_id: str
    kb_name: str
    content_count: str = "0"
    description: str = ""
    base_type: str = ""
    member_count: str = "0"
    role_type: str = ""


@dataclass
class ImaSearchResult:
    """A single search result from IMA knowledge search."""

    title: str
    highlight_content: str = ""
    url: str = ""
    media_id: str = ""


@dataclass
class ImaNote:
    """A note entry from the notes module."""

    note_id: str
    title: str = ""
    summary: str = ""
    create_time: str = ""
    modify_time: str = ""
    cover_image: str = ""
    folder_id: str = ""
    folder_name: str = ""


@dataclass
class ImaSyncResult:
    """Result of a sync operation."""

    pulled: int = 0
    pushed: int = 0
    errors: list[str] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ImaApiError(Exception):
    """IMA API returned an error."""

    # Common IMA OpenAPI error codes → user-friendly (Chinese) hints.
    _FRIENDLY: dict[int, str] = {
        20001: "参数缺失或格式错误，请检查请求字段",
        20002: "知识库不存在或已删除",
        20003: "笔记不存在或已删除",
        20004: "认证失败：Client ID 或 API Key 无效",
        20005: "权限不足，该账号无权操作目标资源",
        20006: "请求频率超限，请稍后重试",
        20007: "内容超长或文件过大",
        20008: "不支持的文件类型",
        20009: "资源数量已达上限",
        20010: "接口未开通，请在 IMA 后台申请权限",
        40001: "COS 上传失败，请检查网络或重试",
        50001: "IMA 服务内部错误，请稍后重试",
    }

    def __init__(self, message: str, code: int = -1) -> None:
        super().__init__(f"[IMA {code}] {message}")
        self.code = code

    def friendly_message(self) -> str:
        """Return a user-facing hint combining the raw message and the mapped hint."""
        hint = self._FRIENDLY.get(self.code)
        if hint:
            return f"{hint}（原始错误：{self.args[0]}）"
        return str(self.args[0])


class ImaConfigError(Exception):
    """IMA credentials not configured."""


# HTTP status codes that should trigger a retry.
_RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}
# IMA business codes that should trigger a retry (rate limit / transient).
_RETRYABLE_IMA_CODES = {20006, 50001}
# Default retry config for the request layer.
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF_BASE = 0.5  # seconds; doubled each retry (capped at 8s)


# ---------------------------------------------------------------------------
# IMA API Client (pure stdlib)
# ---------------------------------------------------------------------------


class ImaClient:
    """HTTP client for IMA OpenAPI, using only urllib.

    Two modules with distinct path prefixes are supported:
        * knowledge-base: /openapi/wiki/v1/<endpoint>
        * notes:          /openapi/note/v1/<endpoint>
    """

    BASE_PATH = "/openapi"

    def __init__(
        self,
        client_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
    ) -> None:
        settings = get_settings()
        self._client_id = client_id or settings.ima_openapi_clientid
        self._api_key = api_key or settings.ima_openapi_apikey
        self._base_url = (base_url or settings.ima_openapi_base_url).rstrip("/")
        self._max_retries = max(1, max_retries)
        self._backoff_base = backoff_base

    def _check_credentials(self) -> None:
        if not self._client_id or not self._api_key:
            raise ImaConfigError(
                "IMA OpenAPI credentials not configured. "
                "Set IMA_OPENAPI_CLIENTID and IMA_OPENAPI_APIKEY in .env"
            )

    def _request(
        self, module_path: str, endpoint: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a POST request to IMA OpenAPI with automatic retry.

        Retries on transient failures (HTTP 429/5xx, IMA codes 20006/50001)
        using exponential backoff. Non-retryable errors propagate immediately.

        Args:
            module_path: Module prefix, e.g. "wiki/v1" or "note/v1".
            endpoint: Endpoint name, e.g. "search_knowledge_base" or "import_doc".
            body: JSON request body.
        """
        last_error: ImaApiError | None = None
        for attempt in range(self._max_retries):
            try:
                return self._request_once(module_path, endpoint, body)
            except ImaApiError as e:
                last_error = e
                if not self._is_retryable(e):
                    raise
                if attempt < self._max_retries - 1:
                    delay = min(self._backoff_base * (2 ** attempt), 8.0)
                    time.sleep(delay)
        # All retries exhausted; re-raise the last error.
        raise last_error  # type: ignore[misc]

    @staticmethod
    def _is_retryable(error: ImaApiError) -> bool:
        """Return True when an error is transient and worth retrying."""
        # IMA business codes take precedence when present (code > 0).
        if error.code in _RETRYABLE_IMA_CODES:
            return True
        # Fall back to HTTP status (negative codes are network errors).
        if error.code in _RETRYABLE_HTTP_STATUS:
            return True
        return False

    def _request_once(
        self, module_path: str, endpoint: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Single attempt: send a POST request to IMA OpenAPI.

        Returns the ``data`` field on success. Raises :class:`ImaApiError`
        on HTTP failure or a non-zero business ``code``.
        """
        self._check_credentials()
        url = f"{self._base_url}{self.BASE_PATH}/{module_path}/{endpoint}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        req.add_header("ima-openapi-clientid", self._client_id)
        req.add_header("ima-openapi-apikey", self._api_key)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                result = json.loads(raw)
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
            raise ImaApiError(f"HTTP {e.code}: {body_text or e.reason}", e.code) from e
        if result.get("code") != 0:
            raise ImaApiError(
                result.get("msg", "unknown error"),
                result.get("code", -1),
            )
        return result.get("data", {})

    # ------------------------------------------------------------------
    # knowledge-base module (wiki/v1)
    # ------------------------------------------------------------------

    def list_knowledge_bases(
        self, query: str = "", limit: int = 20, cursor: str = ""
    ) -> tuple[list[ImaKnowledgeBase], bool, str]:
        """List or search knowledge bases.

        Returns (knowledge_bases, is_end, next_cursor).
        """
        data = self._request(
            KB_PATH,
            "search_knowledge_base",
            {"query": query, "cursor": cursor, "limit": limit},
        )
        kbs = [
            ImaKnowledgeBase(
                kb_id=kb.get("kb_id", ""),
                kb_name=kb.get("kb_name", ""),
                content_count=kb.get("content_count", "0"),
                description=kb.get("description", ""),
                base_type=kb.get("base_type", ""),
                member_count=kb.get("member_count", "0"),
                role_type=kb.get("role_type", ""),
            )
            for kb in data.get("info_list", [])
        ]
        return kbs, data.get("is_end", True), data.get("next_cursor", "")

    def get_addable_knowledge_base_list(
        self, limit: int = 50, cursor: str = ""
    ) -> tuple[list[ImaKnowledgeBase], bool, str]:
        """List knowledge bases that the current user can add content to.

        Returns (knowledge_bases, is_end, next_cursor).
        """
        data = self._request(
            KB_PATH,
            "get_addable_knowledge_base_list",
            {"cursor": cursor, "limit": limit},
        )
        kbs = [
            ImaKnowledgeBase(
                kb_id=kb.get("kb_id", ""),
                kb_name=kb.get("kb_name", ""),
                content_count=kb.get("content_count", "0"),
                description=kb.get("description", ""),
                base_type=kb.get("base_type", ""),
                member_count=kb.get("member_count", "0"),
                role_type=kb.get("role_type", ""),
            )
            for kb in data.get("info_list", [])
        ]
        return kbs, data.get("is_end", True), data.get("next_cursor", "")

    def search_knowledge(
        self, query: str, kb_id: str, cursor: str = ""
    ) -> tuple[list[ImaSearchResult], bool, str]:
        """Search knowledge content in a specific knowledge base.

        Returns (results, is_end, next_cursor).
        """
        data = self._request(
            KB_PATH,
            "search_knowledge",
            {"query": query, "knowledge_base_id": kb_id, "cursor": cursor},
        )
        results = [
            ImaSearchResult(
                title=item.get("title", ""),
                highlight_content=item.get("highlight_content", ""),
                url=item.get("url", ""),
                media_id=item.get("media_id", ""),
            )
            for item in data.get("info_list", [])
        ]
        return results, data.get("is_end", True), data.get("next_cursor", "")

    def get_knowledge_list(
        self, kb_id: str, folder_id: str = "", limit: int = 20, cursor: str = ""
    ) -> dict[str, Any]:
        """Browse knowledge base folder contents."""
        return self._request(
            KB_PATH,
            "get_knowledge_list",
            {
                "knowledge_base_id": kb_id,
                "folder_id": folder_id,
                "limit": limit,
                "cursor": cursor,
            },
        )

    def import_urls(
        self, kb_id: str, urls: list[str], folder_id: str = ""
    ) -> dict[str, Any]:
        """Batch import web pages into a knowledge base by URL.

        IMA fetches and parses each URL server-side, so the caller only
        needs to provide the URLs. Returns the raw API ``data`` field
        (typically a job descriptor; the actual ingestion is asynchronous).

        Args:
            kb_id: Target knowledge base ID.
            urls: List of HTTP/HTTPS URLs to import.
            folder_id: Optional target folder within the knowledge base.
        """
        if not urls:
            raise ImaApiError("urls must not be empty", -1)
        body: dict[str, Any] = {
            "knowledge_base_id": kb_id,
            "urls": list(urls),
        }
        if folder_id:
            body["folder_id"] = folder_id
        return self._request(KB_PATH, "import_urls", body)

    def add_knowledge(
        self,
        kb_id: str,
        media_id: str,
        media_type: int = MEDIA_TYPE_FILE,
        folder_id: str = "",
    ) -> dict[str, Any]:
        """Attach a media (file or note) to a knowledge base.

        Used as step 3 of the file upload flow (``media_type=10`` with the
        ``media_id`` returned by :meth:`create_media`), or to associate an
        existing note with a knowledge base (``media_type=11`` with the
        note's ``note_id``).

        Args:
            kb_id: Target knowledge base ID.
            media_id: For files, the ``media_id`` from create_media.
                For notes, the note's ``note_id``.
            media_type: 10 = uploaded file, 11 = note.
            folder_id: Optional target folder within the knowledge base.
        """
        body: dict[str, Any] = {
            "knowledge_base_id": kb_id,
            "media_id": media_id,
            "media_type": media_type,
        }
        if folder_id:
            body["folder_id"] = folder_id
        return self._request(KB_PATH, "add_knowledge", body)

    def create_media(
        self,
        kb_id: str,
        file_name: str,
        file_size: int,
        content_type: str = "application/octet-stream",
        file_ext: str = "",
    ) -> dict[str, Any]:
        """Step 1 of file upload: register a media record and get COS credentials.

        Returns the raw API ``data`` field, which is expected to contain:
            * ``media_id``      — media record ID, used in add_knowledge
            * ``upload_url``    — pre-signed COS URL for PUT upload
            * ``authorization`` — (optional) COS auth header value
            * ``headers``       — (optional) additional COS headers

        Args:
            kb_id: Target knowledge base ID.
            file_name: File name (with extension).
            file_size: File size in bytes.
            content_type: MIME type (e.g. ``application/pdf``).
            file_ext: File extension without dot (e.g. ``pdf``). If empty,
                derived from ``file_name``.
        """
        if not file_ext:
            file_ext = Path(file_name).suffix.lstrip(".").lower()
        body = {
            "knowledge_base_id": kb_id,
            "file_name": file_name,
            "file_size": file_size,
            "content_type": content_type,
            "file_ext": file_ext,
        }
        return self._request(KB_PATH, "create_media", body)

    def _cos_put(self, upload_url: str, data: bytes, content_type: str = "") -> None:
        """Step 2 of file upload: PUT raw bytes to a pre-signed COS URL.

        The COS URL is pre-signed and does NOT require IMA auth headers.
        Retries on transient HTTP failures (429/5xx) with exponential
        backoff. Raises :class:`ImaApiError` on persistent HTTP failure.
        """
        last_error: ImaApiError | None = None
        for attempt in range(self._max_retries):
            req = urllib.request.Request(upload_url, data=data, method="PUT")
            if content_type:
                req.add_header("Content-Type", content_type)
            req.add_header("Content-Length", str(len(data)))
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    resp.read()  # drain
                return
            except urllib.error.HTTPError as e:
                body_text = ""
                try:
                    body_text = e.read().decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    pass
                last_error = ImaApiError(
                    f"COS PUT failed: HTTP {e.code}: {body_text or e.reason}",
                    e.code,
                )
                if e.code not in _RETRYABLE_HTTP_STATUS:
                    raise last_error from e
                if attempt < self._max_retries - 1:
                    delay = min(self._backoff_base * (2 ** attempt), 8.0)
                    time.sleep(delay)
        raise last_error  # type: ignore[misc]

    def upload_file(
        self,
        kb_id: str,
        file_path: str | Path,
        content_type: str | None = None,
        folder_id: str = "",
    ) -> dict[str, Any]:
        """Full 3-step file upload flow: create_media → COS PUT → add_knowledge.

        Args:
            kb_id: Target knowledge base ID.
            file_path: Local file path to upload.
            content_type: Optional MIME type override. If None, guessed
                from the file extension via :mod:`mimetypes`.
            folder_id: Optional target folder within the knowledge base.

        Returns a dict with ``media_id``, ``kb_id``, and the
        ``add_knowledge`` response. Raises :class:`ImaApiError` if any
        step fails or if the create_media response is missing the
        expected ``upload_url`` / ``media_id`` fields.
        """
        path = Path(file_path)
        if not path.is_file():
            raise ImaApiError(f"file not found: {path}", -1)
        file_size = path.stat().st_size
        file_name = path.name
        if content_type is None:
            guessed, _ = mimetypes.guess_type(file_name)
            content_type = guessed or "application/octet-stream"

        # Step 1: create_media → get COS upload URL + media_id
        media_resp = self.create_media(
            kb_id=kb_id,
            file_name=file_name,
            file_size=file_size,
            content_type=content_type,
        )
        media_id = media_resp.get("media_id") or media_resp.get("MediaId") or ""
        upload_url = media_resp.get("upload_url") or media_resp.get("UploadUrl") or ""
        if not media_id or not upload_url:
            raise ImaApiError(
                f"create_media response missing media_id/upload_url: {media_resp}",
                -1,
            )

        # Step 2: PUT file bytes to COS (no IMA auth headers)
        data = path.read_bytes()
        self._cos_put(upload_url, data, content_type=content_type)

        # Step 3: add_knowledge → attach the uploaded file to the KB
        add_resp = self.add_knowledge(
            kb_id=kb_id,
            media_id=media_id,
            media_type=MEDIA_TYPE_FILE,
            folder_id=folder_id,
        )
        return {
            "media_id": media_id,
            "kb_id": kb_id,
            "file_name": file_name,
            "file_size": file_size,
            "add_knowledge": add_resp,
        }

    # ------------------------------------------------------------------
    # notes module (note/v1)
    # ------------------------------------------------------------------

    def import_doc(
        self,
        content: str,
        title: str | None = None,
        content_format: int = CONTENT_FORMAT_MARKDOWN,
        note_book_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new note via the notes module.

        The IMA notes API uses a single `content` field; the title is
        typically the first markdown heading. If `title` is provided and
        not already present in `content`, it is prepended as an H1.

        Verified: returns ``{"note_id": "..."}`` on success.

        Args:
            content: Note body (markdown when content_format=1).
            title: Optional title. Prepended as `# title\\n\\n` if not in content.
            content_format: 1 = markdown, 0 = plaintext.
            note_book_id: Optional notebook ID to place the note in.
        """
        body_content = content
        if title and title.strip() and title.strip() not in content:
            body_content = f"# {title.strip()}\n\n{content}"
        body: dict[str, Any] = {
            "content_format": content_format,
            "content": body_content,
        }
        if note_book_id:
            body["note_book_id"] = note_book_id
        return self._request(NOTES_PATH, "import_doc", body)

    def append_doc(
        self,
        note_id: str,
        content: str,
        content_format: int = CONTENT_FORMAT_MARKDOWN,
    ) -> dict[str, Any]:
        """Append content to an existing note.

        Verified: accepts ``note_id`` (preferred) or ``doc_id``; returns
        ``{"note_id": "..."}`` on success.

        Args:
            note_id: Target note ID (from list_note / search_note_book).
            content: Content to append (markdown when content_format=1).
            content_format: 1 = markdown, 0 = plaintext.
        """
        return self._request(
            NOTES_PATH,
            "append_doc",
            {
                "note_id": note_id,
                "content_format": content_format,
                "content": content,
            },
        )

    def search_note_book(
        self, query: str, start: int = 0, end: int = 20, search_type: int = 0
    ) -> tuple[list[ImaNote], bool, int]:
        """Search notes by title.

        Verified response fields: ``docs`` (list of {doc: {basic_info: {...}}}),
        ``is_end`` (bool), ``total_hit_num`` (string-encoded int).

        Args:
            query: Search keyword.
            start: Pagination start offset.
            end: Pagination end offset (exclusive).
            search_type: 0 = by title, 1 = by content (full-text).

        Returns (notes, is_end, total_hit_num).
        """
        data = self._request(
            NOTES_PATH,
            "search_note_book",
            {
                "search_type": search_type,
                "query_info": {"title": query},
                "start": start,
                "end": end,
            },
        )
        # Each item in `docs` has shape {"doc": {"basic_info": {...}}}
        # Flatten before parsing.
        flat_items = [
            (item.get("doc", {}) or {}).get("basic_info", {}) or {}
            for item in data.get("docs", [])
        ]
        notes = [self._parse_search_note(bi) for bi in flat_items]
        # total_hit_num is returned as a string in the live API.
        try:
            total = int(data.get("total_hit_num", 0))
        except (TypeError, ValueError):
            total = 0
        return notes, data.get("is_end", False), total

    def list_note(self, limit: int = 20, cursor: str = "") -> tuple[list[ImaNote], bool, str]:
        """List notes in the user's account.

        Verified: body uses lowercase ``limit`` but capitalized ``Cursor``.
        Response returns ``note_book_list`` (list) and ``is_end`` (bool).
        The endpoint does NOT echo back a next cursor; pagination
        terminates when ``is_end`` is True.

        Returns (notes, is_end, next_cursor).
        """
        data = self._request(
            NOTES_PATH,
            "list_note",
            {"limit": limit, "Cursor": cursor},
        )
        notes = [self._parse_note(item) for item in data.get("note_book_list", [])]
        return notes, data.get("is_end", True), data.get("next_cursor", "")

    def get_doc_content(self, note_id: str) -> dict[str, Any]:
        """Fetch the full content of a note by its note_id.

        Verified: accepts ``note_id`` (preferred) or ``doc_id``.
        """
        return self._request(NOTES_PATH, "get_doc_content", {"note_id": note_id})

    @staticmethod
    def _parse_note(item: dict[str, Any]) -> ImaNote:
        """Parse a note dict from list_note responses.

        ``list_note`` returns items with fields: note_id, title, summary,
        create_time, modify_time, cover_image, note_ext_info.{folder_id,
        folder_name}.
        """
        ext = item.get("note_ext_info") or {}
        return ImaNote(
            note_id=item.get("note_id", item.get("doc_id", "")),
            title=item.get("title", ""),
            summary=item.get("summary", ""),
            create_time=item.get("create_time", ""),
            modify_time=item.get("modify_time", item.get("update_time", "")),
            cover_image=item.get("cover_image", ""),
            folder_id=ext.get("folder_id", ""),
            folder_name=ext.get("folder_name", ""),
        )

    @staticmethod
    def _parse_search_note(basic_info: dict[str, Any]) -> ImaNote:
        """Parse a basic_info dict from search_note_book responses.

        ``search_note_book`` flattens to basic_info with fields: docid
        (note the missing underscore), title, summary, create_time,
        modify_time, status, folder_id, folder_name.
        """
        return ImaNote(
            note_id=basic_info.get("docid", basic_info.get("note_id", "")),
            title=basic_info.get("title", ""),
            summary=basic_info.get("summary", ""),
            create_time=basic_info.get("create_time", ""),
            modify_time=basic_info.get("modify_time", ""),
            folder_id=basic_info.get("folder_id", ""),
            folder_name=basic_info.get("folder_name", ""),
        )

    # ------------------------------------------------------------------
    # Backward-compatible alias
    # ------------------------------------------------------------------

    def create_note(
        self, kb_id: str, title: str, content: str
    ) -> dict[str, Any]:
        """Create a note in a knowledge base (backward-compatible alias).

        Note: IMA's notes module (`import_doc`) creates personal notes and
        does not accept a `kb_id`. To associate a created note with a
        knowledge base, use the knowledge-base module's `add_knowledge`
        with `media_type=11`. This alias keeps the old call signature
        working by delegating to `import_doc` and ignoring `kb_id`.
        """
        return self.import_doc(content=content, title=title)


# ---------------------------------------------------------------------------
# Sync Service
# ---------------------------------------------------------------------------


class ImaSyncService:
    """Bidirectional sync between Hermes memory and IMA knowledge bases.

    - pull: IMA → Hermes (search IMA, store results as L2 episodes)
    - push: Hermes → IMA (create notes in IMA from Hermes knowledge docs)
    - sync: bidirectional (pull + push)
    """

    def __init__(
        self,
        client: ImaClient | None = None,
        memory: MemoryService | None = None,
    ) -> None:
        self._client = client or ImaClient()
        self._memory = memory

    def list_kbs(self, query: str = "") -> list[ImaKnowledgeBase]:
        """List knowledge bases (convenience method)."""
        kbs, _, _ = self._client.list_knowledge_bases(query=query)
        return kbs

    def pull(
        self, query: str, kb_id: str, limit: int = 20
    ) -> list[ImaSearchResult]:
        """Pull knowledge from IMA into Hermes L2 episodes.

        Searches IMA for *query* in knowledge base *kb_id*, records each
        result as an L2 episode in Hermes memory.
        """
        results: list[ImaSearchResult] = []
        cursor = ""
        while len(results) < limit:
            batch, is_end, cursor = self._client.search_knowledge(
                query, kb_id, cursor
            )
            results.extend(batch)
            if is_end or not batch:
                break
            results = results[:limit]

        if self._memory:
            for r in results:
                self._memory.record_episode(
                    make_episode(
                        "ima_pull",
                        f"[IMA] {r.title}",
                        {
                            "source": "ima",
                            "query": query,
                            "kb_id": kb_id,
                            "content": r.highlight_content,
                            "url": r.url,
                        },
                    )
                )
        return results

    def push(self, kb_id: str, title: str, content: str) -> dict[str, Any]:
        """Push a piece of knowledge to IMA as a note.

        Records the push as an L2 episode in Hermes memory.

        Note: `kb_id` is preserved in the episode metadata for traceability,
        but the underlying IMA `import_doc` endpoint creates a personal note
        not bound to a specific knowledge base.
        """
        result = self._client.create_note(kb_id, title, content)
        if self._memory:
            self._memory.record_episode(
                make_episode(
                    "ima_push",
                    f"[IMA Push] {title}",
                    {
                        "kb_id": kb_id,
                        "title": title,
                        "content_length": len(content),
                    },
                )
            )
        return result

    def push_urls(
        self, kb_id: str, urls: list[str], folder_id: str = ""
    ) -> dict[str, Any]:
        """Push web page URLs to an IMA knowledge base.

        Records the push as an L2 episode in Hermes memory.
        """
        result = self._client.import_urls(kb_id, urls, folder_id=folder_id)
        if self._memory:
            self._memory.record_episode(
                make_episode(
                    "ima_push_urls",
                    f"[IMA Push URLs] {len(urls)} url(s) -> {kb_id}",
                    {
                        "kb_id": kb_id,
                        "urls": list(urls),
                        "folder_id": folder_id,
                        "count": len(urls),
                    },
                )
            )
        return result

    def push_file(
        self,
        kb_id: str,
        file_path: str | Path,
        content_type: str | None = None,
        folder_id: str = "",
    ) -> dict[str, Any]:
        """Upload a local file to an IMA knowledge base (3-step flow).

        Records the upload as an L2 episode in Hermes memory.
        """
        result = self._client.upload_file(
            kb_id, file_path, content_type=content_type, folder_id=folder_id
        )
        if self._memory:
            self._memory.record_episode(
                make_episode(
                    "ima_push_file",
                    f"[IMA Push File] {result.get('file_name', '')} -> {kb_id}",
                    {
                        "kb_id": kb_id,
                        "file_name": result.get("file_name", ""),
                        "file_size": result.get("file_size", 0),
                        "media_id": result.get("media_id", ""),
                        "folder_id": folder_id,
                    },
                )
            )
        return result

    def push_episodes(
        self, kb_id: str, kind: str | None = None, limit: int = 10
    ) -> ImaSyncResult:
        """Push recent Hermes L2 episodes to IMA as notes.

        Each episode's summary becomes the note title, and its details
        become the note content (JSON-serialized).
        """
        result = ImaSyncResult()
        if not self._memory:
            result.errors.append("memory service not configured")
            return result
        episodes = self._memory.list_episodes(kind=kind, limit=limit)
        for ep in episodes:
            try:
                content = json.dumps(ep.details, ensure_ascii=False, indent=2)
                self._client.create_note(kb_id, ep.summary, content)
                result.pushed += 1
                result.details.append(
                    {"title": ep.summary, "episode_id": ep.id, "ok": True}
                )
            except Exception as e:  # noqa: BLE001
                result.errors.append(f"{ep.summary}: {e}")
                result.details.append(
                    {"title": ep.summary, "episode_id": ep.id, "ok": False, "error": str(e)}
                )
        return result

    def sync(
        self, query: str, kb_id: str, push_kind: str | None = None
    ) -> ImaSyncResult:
        """Bidirectional sync: pull from IMA, then push Hermes episodes to IMA.

        Args:
            query: Search query for pulling from IMA.
            kb_id: Target knowledge base ID.
            push_kind: Optional episode kind filter for pushing to IMA.
        """
        result = ImaSyncResult()
        # Pull
        try:
            pulled = self.pull(query, kb_id)
            result.pulled = len(pulled)
        except Exception as e:  # noqa: BLE001
            result.errors.append(f"pull: {e}")
        # Push
        try:
            push_result = self.push_episodes(kb_id, kind=push_kind, limit=10)
            result.pushed = push_result.pushed
            result.errors.extend(push_result.errors)
            result.details.extend(push_result.details)
        except Exception as e:  # noqa: BLE001
            result.errors.append(f"push: {e}")
        return result
