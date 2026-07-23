#!/usr/bin/env python3
"""Skill Manager - 管理所有已安装的skill"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


DEFAULT_SKILLS_DIR = ".trae/skills"
LOCKFILE_NAME = ".skills_store_lock.json"


def load_lockfile(skills_dir: Path) -> dict:
    """加载技能锁文件"""
    lock_path = skills_dir / LOCKFILE_NAME
    if not lock_path.exists():
        return {"version": 1, "skills": {}}
    try:
        with open(lock_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except json.JSONDecodeError:
        return {"version": 1, "skills": {}}
    if not isinstance(raw, dict):
        return {"version": 1, "skills": {}}
    if not isinstance(raw.get("skills"), dict):
        raw["skills"] = {}
    return raw


def save_lockfile(skills_dir: Path, lock: dict) -> None:
    """保存技能锁文件"""
    skills_dir.mkdir(parents=True, exist_ok=True)
    lock_path = skills_dir / LOCKFILE_NAME
    with open(lock_path, 'w', encoding='utf-8') as f:
        json.dump(lock, f, indent=2, ensure_ascii=False)


def cmd_list(args: argparse.Namespace) -> None:
    """列出所有已安装的技能"""
    skills_dir = Path(args.dir).expanduser().resolve()
    lock = load_lockfile(skills_dir)
    skills = lock.get("skills", {})
    
    if not skills:
        print("No installed skills.")
        return
    
    print("Installed skills:")
    print("-" * 80)
    for slug, info in skills.items():
        name = info.get("name", slug)
        version = info.get("version", "")
        source = info.get("source", "local")
        print(f"{slug}")
        print(f"  Name:     {name}")
        print(f"  Version:  {version}")
        print(f"  Source:   {source}")
        print(f"  Path:     {skills_dir / slug}")
        print("-" * 80)


def cmd_install(args: argparse.Namespace) -> None:
    """安装新技能"""
    skills_dir = Path(args.dir).expanduser().resolve()
    target_dir = skills_dir / args.slug
    
    if target_dir.exists():
        print(f"Skill {args.slug} is already installed.")
        return
    
    # 创建技能目录
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建基本的SKILL.md文件
    skill_md = target_dir / "SKILL.md"
    skill_md.write_text(f"""---
name: {args.slug}
description: Skill {args.slug}
---

# {args.slug}

This is a skill for {args.slug}.
""", encoding='utf-8')
    
    # 更新锁文件
    lock = load_lockfile(skills_dir)
    lock["skills"][args.slug] = {
        "name": args.slug,
        "version": "1.0.0",
        "source": "local",
        "installed_at": "local"
    }
    save_lockfile(skills_dir, lock)
    
    print(f"Installed: {args.slug} -> {target_dir}")


def cmd_uninstall(args: argparse.Namespace) -> None:
    """卸载技能"""
    skills_dir = Path(args.dir).expanduser().resolve()
    target_dir = skills_dir / args.slug
    
    if not target_dir.exists():
        print(f"Skill {args.slug} is not installed.")
        return
    
    # 删除技能目录
    shutil.rmtree(target_dir)
    
    # 更新锁文件
    lock = load_lockfile(skills_dir)
    if args.slug in lock["skills"]:
        del lock["skills"][args.slug]
        save_lockfile(skills_dir, lock)
    
    print(f"Uninstalled: {args.slug}")


def cmd_search(args: argparse.Namespace) -> None:
    """搜索技能"""
    print(f"Searching for skills related to: {' '.join(args.query)}")
    print("Note: This is a placeholder for skillhub search functionality.")
    print("In a real implementation, this would query skillhub API.")


def cmd_update(args: argparse.Namespace) -> None:
    """更新技能"""
    skills_dir = Path(args.dir).expanduser().resolve()
    lock = load_lockfile(skills_dir)
    
    if args.slug:
        # 更新特定技能
        if args.slug not in lock["skills"]:
            print(f"Skill {args.slug} is not installed.")
            return
        print(f"Updating skill: {args.slug}")
        print("Note: This is a placeholder for skill update functionality.")
    else:
        # 更新所有技能
        print("Updating all skills...")
        for slug in lock["skills"]:
            print(f"- {slug}")
        print("Note: This is a placeholder for batch skill update functionality.")


def cmd_config(args: argparse.Namespace) -> None:
    """管理技能配置"""
    skills_dir = Path(args.dir).expanduser().resolve()
    target_dir = skills_dir / args.slug
    
    if not target_dir.exists():
        print(f"Skill {args.slug} is not installed.")
        return
    
    config_path = target_dir / "config.json"
    
    if not args.key:
        # 查看配置
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            print(f"Configuration for {args.slug}:")
            print(json.dumps(config, indent=2, ensure_ascii=False))
        else:
            print(f"No configuration file found for {args.slug}.")
    else:
        # 修改配置
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}
        
        config[args.key] = args.value
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"Updated configuration for {args.slug}:")
        print(f"  {args.key}: {args.value}")


def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(description="Skill Manager")
    parser.add_argument("--dir", default=DEFAULT_SKILLS_DIR, help="Skills directory")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # list command
    list_parser = subparsers.add_parser("list", help="List installed skills")
    
    # install command
    install_parser = subparsers.add_parser("install", help="Install a skill")
    install_parser.add_argument("slug", help="Skill slug")
    
    # uninstall command
    uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall a skill")
    uninstall_parser.add_argument("slug", help="Skill slug")
    
    # search command
    search_parser = subparsers.add_parser("search", help="Search for skills")
    search_parser.add_argument("query", nargs="+", help="Search query")
    
    # update command
    update_parser = subparsers.add_parser("update", help="Update skills")
    update_parser.add_argument("slug", nargs="?", help="Skill slug (optional, update all if not specified)")
    
    # config command
    config_parser = subparsers.add_parser("config", help="Manage skill configuration")
    config_parser.add_argument("slug", help="Skill slug")
    config_parser.add_argument("key", nargs="?", help="Configuration key")
    config_parser.add_argument("value", nargs="?", help="Configuration value")
    
    args = parser.parse_args()
    
    if args.command == "list":
        cmd_list(args)
    elif args.command == "install":
        cmd_install(args)
    elif args.command == "uninstall":
        cmd_uninstall(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "config":
        cmd_config(args)


if __name__ == "__main__":
    main()