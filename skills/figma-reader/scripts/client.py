"""
figma-reader 共享 client.py

封装 Figma REST API 的 4 个核心端点：
- GET /v1/files/{file_key}
- GET /v1/files/{file_key}/nodes
- GET /v1/images/{file_key}
- GET /v1/files/{file_key}/components

特性：
- 自动处理 X-Figma-Token 认证
- 429 限流自动退避
- 统一异常类型
- mock 模式（无 token 时返回 fixture）
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

FIGMA_API_BASE = "https://api.figma.com/v1"
DEFAULT_TIMEOUT = 30
RATE_LIMIT_BACKOFF = 60  # 秒


class FigmaError(Exception):
    """Figma API 错误基类"""


class FigmaAuthError(FigmaError):
    """认证失败（401/403）"""


class FigmaNotFoundError(FigmaError):
    """资源不存在（404）"""


class FigmaRateLimitError(FigmaError):
    """触发限流（429）"""


class FigmaClient:
    """Figma REST API 客户端"""

    def __init__(
        self,
        token: Optional[str] = None,
        mock: bool = False,
        mock_data_dir: Optional[Path] = None,
    ):
        self.token = token or os.environ.get("FIGMA_TOKEN", "")
        self.mock = mock or not self.token
        self.mock_data_dir = mock_data_dir or (Path(__file__).parent.parent / "data")
        if not self.mock and not HAS_REQUESTS:
            raise ImportError("requests 未安装，请先 pip install requests")

    def _request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """底层请求方法"""
        if self.mock:
            return self._mock_request(endpoint, params)

        url = f"{FIGMA_API_BASE}{endpoint}"
        headers = {"X-Figma-Token": self.token}
        for attempt in range(3):
            try:
                resp = requests.get(
                    url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT
                )
            except requests.RequestException as e:
                raise FigmaError(f"网络错误: {e}") from e

            if resp.status_code == 401 or resp.status_code == 403:
                raise FigmaAuthError("Token 无效或权限不足")
            if resp.status_code == 404:
                raise FigmaNotFoundError(f"资源不存在: {url}")
            if resp.status_code == 429:
                if attempt < 2:
                    time.sleep(RATE_LIMIT_BACKOFF)
                    continue
                raise FigmaRateLimitError("触发限流（60 req/min）")
            if resp.status_code >= 400:
                raise FigmaError(f"HTTP {resp.status_code}: {resp.text[:200]}")

            return resp.json()

        raise FigmaRateLimitError("重试 3 次仍触发限流")

    def _mock_request(self, endpoint: str, params: Optional[Dict]) -> Dict:
        """Mock 模式：从本地 fixture 读取"""
        sample = self.mock_data_dir / "sample_response.json"
        if not sample.exists():
            return {
                "mock": True,
                "endpoint": endpoint,
                "params": params,
                "document": {"id": "0:0", "name": "Mock Document", "children": []},
            }
        data = json.loads(sample.read_text(encoding="utf-8"))
        # 顺序很重要：先匹配更具体的路径
        if "/components" in endpoint:
            return data.get("components_response", data)
        if "/images" in endpoint:
            return data.get("images_response", data)
        if "/nodes" in endpoint:
            return data.get("nodes_response", data)
        if "/files" in endpoint:
            return data.get("file_response", data)
        return data

    # === 4 个核心端点封装 ===

    def get_file(
        self,
        file_key: str,
        depth: Optional[int] = None,
        geometry: bool = False,
    ) -> Dict:
        """GET /v1/files/{file_key}"""
        params: Dict[str, Any] = {}
        if depth is not None:
            params["depth"] = depth
        if geometry:
            params["geometry"] = "true"
        return self._request(f"/files/{file_key}", params)

    def get_nodes(self, file_key: str, node_ids: List[str]) -> Dict:
        """GET /v1/files/{file_key}/nodes"""
        return self._request(
            f"/files/{file_key}/nodes",
            {"ids": ",".join(node_ids)},
        )

    def get_images(
        self,
        file_key: str,
        node_ids: List[str],
        fmt: str = "png",
        scale: float = 1.0,
    ) -> Dict:
        """GET /v1/images/{file_key}"""
        valid_fmts = {"png", "jpg", "svg", "pdf"}
        if fmt not in valid_fmts:
            raise ValueError(f"fmt 必须是 {valid_fmts} 之一")
        return self._request(
            f"/images/{file_key}",
            {
                "ids": ",".join(node_ids),
                "format": fmt,
                "scale": scale,
            },
        )

    def get_components(self, file_key: str) -> Dict:
        """GET /v1/files/{file_key}/components"""
        return self._request(f"/files/{file_key}/components")


def download_image(url: str, output_path: Path, timeout: int = 60) -> int:
    """下载图片到本地（字节数）"""
    if not HAS_REQUESTS:
        raise ImportError("requests 未安装")
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    return len(resp.content)
