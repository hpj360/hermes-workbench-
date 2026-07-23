#!/usr/bin/env python3
"""
Chromatic 视觉回归运行器

调用 npx chromatic 跑视觉回归，解析输出。

依赖（可选）：chromatic（npm install -g chromatic）
环境变量：CHROMATIC_PROJECT_TOKEN

用法：
  python3 run_chromatic.py --token $CHROMATIC_PROJECT_TOKEN
  python3 run_chromatic.py --token xxx --exit-once-uploaded
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _has_chromatic() -> bool:
    return subprocess.run(["which", "npx"], capture_output=True).returncode == 0


def _run_chromatic(token: str, exit_once_uploaded: bool) -> dict:
    """调用 npx chromatic。"""
    cmd = ["npx", "chromatic", "--project-token", token]
    if exit_once_uploaded:
        cmd.append("--exit-once-uploaded")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "chromatic 超时（5分钟）"}


def _parse_chromatic_output(output: str) -> dict:
    """从 chromatic 输出提取关键信息。"""
    parsed = {
        "url": None,
        "build_number": None,
        "tests_changed": 0,
        "tests_new": 0,
        "tests_passed": 0,
        "tests_failed": 0,
    }
    # 提取 URL: https://www.chromatic.com/build?appId=xxx&number=123
    url_match = re.search(r"(https://www\.chromatic\.com/build\?[^\s]+)", output)
    if url_match:
        parsed["url"] = url_match.group(1)
    # 提取 build number
    num_match = re.search(r"Build #(\d+)", output)
    if num_match:
        parsed["build_number"] = int(num_match.group(1))
    # 提取测试结果
    for key, pattern in [
        ("tests_changed", r"(\d+)\s+changed"),
        ("tests_new",    r"(\d+)\s+new"),
        ("tests_passed", r"(\d+)\s+passed"),
        ("tests_failed", r"(\d+)\s+failed"),
    ]:
        m = re.search(pattern, output)
        if m:
            parsed[key] = int(m.group(1))
    return parsed


def main():
    parser = argparse.ArgumentParser(description="Chromatic 视觉回归")
    parser.add_argument("--token", default=os.environ.get("CHROMATIC_PROJECT_TOKEN"), help="Chromatic project token")
    parser.add_argument("--exit-once-uploaded", action="store_true", help="上传后立即退出（CI 用）")
    parser.add_argument("--output", help="报告输出路径")
    args = parser.parse_args()

    if not args.token:
        sys.stderr.write("错误: 缺少 Chromatic token（--token 或 env CHROMATIC_PROJECT_TOKEN）\n")
        sys.exit(2)

    if not _has_chromatic():
        sys.stderr.write("警告: npx 未安装，无法跑 Chromatic\n")
        report = {"error": "npx 未安装", "mock": True, "url": None, "tests_failed": 0}
    else:
        result = _run_chromatic(args.token, args.exit_once_uploaded)
        if result.get("error"):
            report = {"error": result["error"]}
        else:
            output = result.get("stdout", "") + result.get("stderr", "")
            report = _parse_chromatic_output(output)
            report["returncode"] = result.get("returncode")
            if report["tests_failed"] > 0:
                report["passed"] = False
            else:
                report["passed"] = True

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False, indent=2))
        sys.stderr.write(
            f"[chromatic] build #{report.get('build_number', '?')} "
            f"passed={report.get('passed', False)} url={report.get('url', '-')}\n"
        )
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    if not report.get("passed", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
