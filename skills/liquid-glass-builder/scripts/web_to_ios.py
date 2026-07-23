#!/usr/bin/env python3
"""
web_to_ios.py - Web Glass 组件 → iOS SwiftUI 草稿转换器

功能：
  解析 web/GlassPanel.tsx 的 props，生成对应的 SwiftUI LiquidGlassView 调用代码。

用法：
  python3 scripts/web_to_ios.py --props blur=24,alpha=0.6,highlight=true
  python3 scripts/web_to_ios.py --from-file web/example.tsx
  python3 scripts/web_to_ios.py --interactive
"""

import argparse
import re
import sys
from pathlib import Path


def parse_props(props_str: str) -> dict:
    """解析 blur=24,alpha=0.6,highlight=true 形式"""
    props = {}
    for pair in props_str.split(','):
        if '=' not in pair:
            continue
        k, v = pair.split('=', 1)
        k = k.strip()
        v = v.strip()
        if v.lower() == 'true':
            props[k] = True
        elif v.lower() == 'false':
            props[k] = False
        else:
            try:
                props[k] = int(v)
            except ValueError:
                try:
                    props[k] = float(v)
                except ValueError:
                    props[k] = v
    return props


def extract_props_from_tsx(tsx_path: Path) -> dict:
    """从 TSX 文件提取 GlassPanel 的 props"""
    content = tsx_path.read_text(encoding='utf-8')
    # 简单匹配 <GlassPanel blur={24} alpha={0.6} ...>
    match = re.search(r'<GlassPanel([^/>]*)/?>', content, re.DOTALL)
    if not match:
        return {}
    props_str = match.group(1)
    props = {}
    for m in re.finditer(r'(\w+)\s*=\s*\{([^}]+)\}', props_str):
        key = m.group(1)
        val = m.group(2).strip()
        if val in ('true', 'false'):
            props[key] = val == 'true'
        else:
            try:
                props[key] = float(val) if '.' in val else int(val)
            except ValueError:
                # 去掉引号
                props[key] = val.strip('"\'')
    return props


def generate_swiftui(props: dict, content: str = '/* content */') -> str:
    """生成 SwiftUI 代码"""
    blur = props.get('blur', 24)
    alpha = props.get('alpha', 0.6)
    corner_radius = props.get('radius', 12)
    highlight = props.get('highlight', True)
    dispersion = props.get('dispersion', False)

    dispersion_str = ',\n    dispersion: true' if dispersion else ''
    highlight_str = '' if highlight else ',\n    highlight: false'

    return f"""@available(iOS 17.0, *)
struct GeneratedGlassView: View {{
    var body: some View {{
        LiquidGlassView(
            blur: {blur},
            alpha: {alpha},
            cornerRadius: {corner_radius}{highlight_str}{dispersion_str}
        ) {{
            {content}
        }}
    }}
}}
"""


def main():
    parser = argparse.ArgumentParser(
        description="Web Glass 组件 → iOS SwiftUI 转换器"
    )
    parser.add_argument('--props', help='props 字符串，如 blur=24,alpha=0.6')
    parser.add_argument('--from-file', help='从 TSX 文件提取 props')
    parser.add_argument('--content', default='Text("Hello")', help='占位内容代码')
    parser.add_argument('--output', '-o', help='输出文件（默认 stdout）')
    args = parser.parse_args()

    if args.from_file:
        tsx_path = Path(args.from_file)
        if not tsx_path.exists():
            print(f"❌ 文件不存在: {tsx_path}", file=sys.stderr)
            sys.exit(1)
        props = extract_props_from_tsx(tsx_path)
    elif args.props:
        props = parse_props(args.props)
    else:
        print("❌ 必须提供 --props 或 --from-file", file=sys.stderr)
        sys.exit(1)

    if not props:
        print("⚠️ 未能解析 props，使用默认值", file=sys.stderr)

    swift_code = generate_swiftui(props, args.content)

    if args.output:
        Path(args.output).write_text(swift_code, encoding='utf-8')
        print(f"✅ 已写入: {args.output}")
    else:
        print(swift_code)


if __name__ == '__main__':
    main()
