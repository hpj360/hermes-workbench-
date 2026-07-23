#!/usr/bin/env python3
"""
Skill 打包验证器

验证 Skill 包结构完整性 + 与 skill-creator 评估器兼容

用法：
  python3 package_skill.py <skill_dir> [--output skill.zip]
"""

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path


REQUIRED_FILES = ["SKILL.md", "_meta.json"]
RECOMMENDED_DIRS = ["references", "scripts", "data", "tokens"]


def validate(skill_dir: str) -> dict:
    """验证 Skill 包结构。"""
    skill_path = Path(skill_dir)
    if not skill_path.is_dir():
        raise FileNotFoundError(f"Skill 目录不存在: {skill_dir}")

    issues = []
    info = {
        "path": str(skill_path),
        "name": skill_path.name,
        "files": [],
        "dirs": [],
        "size_bytes": 0,
        "estimated_tokens": 0,
    }

    # 必填文件
    for f in REQUIRED_FILES:
        if not (skill_path / f).exists():
            issues.append({
                "severity": "critical",
                "type": "missing_required_file",
                "message": f"缺失必填文件: {f}",
            })
        else:
            info["files"].append(f)

    # 推荐目录
    for d in RECOMMENDED_DIRS:
        if (skill_path / d).is_dir():
            info["dirs"].append(d)

    # 扫描所有文件
    total_size = 0
    total_chars = 0
    for f in skill_path.rglob("*"):
        if f.is_file():
            rel = f.relative_to(skill_path)
            info["files"].append(str(rel))
            size = f.stat().st_size
            total_size += size
            if f.suffix in (".md", ".txt", ".json", ".py", ".js", ".ts", ".css", ".html", ".vue", ".jsx", ".tsx"):
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    total_chars += len(content)
                except OSError:
                    pass
    info["size_bytes"] = total_size
    info["estimated_tokens"] = total_chars // 4  # 粗略估计 4 字符/token

    # SKILL.md frontmatter 验证
    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        content = skill_md.read_text(encoding="utf-8")
        if not content.startswith("---"):
            issues.append({
                "severity": "critical",
                "type": "missing_frontmatter",
                "message": "SKILL.md 缺少 YAML frontmatter（以 --- 开头）",
            })
        else:
            end = content.find("---", 3)
            if end == -1:
                issues.append({
                    "severity": "critical",
                    "type": "incomplete_frontmatter",
                    "message": "SKILL.md frontmatter 未正确闭合",
                })
            else:
                fm = content[3:end].strip()
                if "name:" not in fm:
                    issues.append({
                        "severity": "critical",
                        "type": "missing_name_field",
                        "message": "frontmatter 缺少 name 字段",
                    })
                if "description:" not in fm:
                    issues.append({
                        "severity": "critical",
                        "type": "missing_description_field",
                        "message": "frontmatter 缺少 description 字段",
                    })
                else:
                    # 提取 description 长度
                    desc_match = [line for line in fm.split("\n") if line.startswith("description:")]
                    if desc_match:
                        desc = desc_match[0].split(":", 1)[1].strip().strip("'\"")
                        if len(desc) < 20:
                            issues.append({
                                "severity": "warning",
                                "type": "short_description",
                                "message": f"description 长度 {len(desc)} 字符 < 20，可能影响触发准确率",
                            })

    # _meta.json 验证
    meta = skill_path / "_meta.json"
    if meta.exists():
        try:
            meta_data = json.loads(meta.read_text(encoding="utf-8"))
            info["meta"] = meta_data
        except json.JSONDecodeError as e:
            issues.append({
                "severity": "critical",
                "type": "invalid_meta_json",
                "message": f"_meta.json 解析失败: {e}",
            })

    # SKILL.md 大小警告
    if skill_md.exists():
        size = skill_md.stat().st_size
        if size > 100_000:  # 100KB
            issues.append({
                "severity": "warning",
                "type": "skill_md_too_large",
                "message": f"SKILL.md 大小 {size/1024:.1f}KB > 100KB，建议精简或拆分到 references/",
            })
        if size < 500:
            issues.append({
                "severity": "warning",
                "type": "skill_md_too_small",
                "message": f"SKILL.md 大小 {size} 字节 < 500，可能内容不完整",
            })

    return {
        "info": info,
        "issues": issues,
        "passed": not any(i["severity"] == "critical" for i in issues),
    }


def package(skill_dir: str, output_path: str) -> str:
    """打包为 zip。"""
    skill_path = Path(skill_dir)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in skill_path.rglob("*"):
            if f.is_file():
                arcname = f.relative_to(skill_path.parent)
                zf.write(f, arcname)
    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="Skill 打包验证器")
    parser.add_argument("skill_dir", help="Skill 目录")
    parser.add_argument("--output", help="打包 zip 路径（可选）")
    args = parser.parse_args()

    result = validate(args.skill_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.output:
        zip_path = package(args.skill_dir, args.output)
        sys.stderr.write(f"[package] 已打包: {zip_path}\n")

    if not result["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
