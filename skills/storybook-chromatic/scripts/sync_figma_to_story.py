#!/usr/bin/env python3
"""
从 Figma 组件生成 Storybook 故事

输入：Figma file_key + 组件 key
输出：React 组件骨架 + CSF 3.0 story 文件

依赖：figma-reader skill（figma_client.py）

用法：
  python3 sync_figma_to_story.py --figma-key ABC123 --component-key btn1 --output src/components/Button/
  python3 sync_figma_to_story.py --figma-key ABC123 --all --output src/
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


def _import_figma_client():
    """从 figma-reader skill 导入。"""
    figma_reader = Path(__file__).parent.parent.parent / "figma-reader" / "scripts"
    if not figma_reader.exists():
        raise FileNotFoundError("figma-reader skill 未安装")
    sys.path.insert(0, str(figma_reader))
    from figma_client import list_components, get_nodes
    return list_components, get_nodes


def _to_pascal_case(s: str) -> str:
    """Button/Primary → ButtonPrimary，'btn-primary' → BtnPrimary。"""
    s = re.sub(r"[^\w]", " ", s)
    parts = s.split()
    return "".join(p.capitalize() for p in parts if p)


def _to_camel_case(s: str) -> str:
    """variant primary → variant，Button/Primary → buttonPrimary。"""
    s = re.sub(r"[^\w]", " ", s)
    parts = s.split()
    if not parts:
        return "value"
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:] if p)


def generate_component_stub(name: str, description: str = "") -> str:
    """生成 React 组件骨架。"""
    return f"""import React from 'react';

export interface {name}Props {{
  /** 组件变体 */
  variant?: 'primary' | 'secondary' | 'ghost';
  /** 尺寸 */
  size?: 'sm' | 'md' | 'lg';
  /** 是否禁用 */
  disabled?: boolean;
  /** 子内容 */
  children?: React.ReactNode;
  /** 点击事件 */
  onClick?: () => void;
}}

/**
 * {description or name + ' 组件'}
 *
 * @example
 * <{name} variant="primary" size="md">Click me</{name}>
 */
export const {name}: React.FC<{name}Props> = ({{
  variant = 'primary',
  size = 'md',
  disabled = false,
  children,
  onClick,
}}) => {{
  return (
    <button
      className={{`btn btn-${{variant}} btn-${{size}}`}}
      disabled={{disabled}}
      onClick={{onClick}}
    >
      {{children}}
    </button>
  );
}};

export default {name};
"""


def generate_story(name: str, description: str = "") -> str:
    """生成 CSF 3.0 story。"""
    return f"""import type {{ Meta, StoryObj }} from '@storybook/react';
import {{ {name} }} from './{name}';

const meta: Meta<typeof {name}> = {{
  title: 'Components/{name}',
  component: {name},
  parameters: {{
    layout: 'centered',
    docs: {{
      description: {{
        component: `{description or name + ' 组件故事'}`,
      }},
    }},
  }},
  tags: ['autodocs'],
  argTypes: {{
    variant: {{
      control: {{ type: 'select' }},
      options: ['primary', 'secondary', 'ghost'],
      description: '视觉变体',
    }},
    size: {{
      control: {{ type: 'select' }},
      options: ['sm', 'md', 'lg'],
      description: '尺寸',
    }},
    disabled: {{ control: 'boolean', description: '是否禁用' }},
  }},
}};
export default meta;
type Story = StoryObj<typeof {name}>;

export const Primary: Story = {{
  args: {{
    variant: 'primary',
    size: 'md',
    children: 'Primary',
  }},
}};

export const Secondary: Story = {{
  args: {{
    variant: 'secondary',
    size: 'md',
    children: 'Secondary',
  }},
}};

export const Ghost: Story = {{
  args: {{
    variant: 'ghost',
    size: 'md',
    children: 'Ghost',
  }},
}};

export const Large: Story = {{
  args: {{
    variant: 'primary',
    size: 'lg',
    children: 'Large',
  }},
}};

export const Disabled: Story = {{
  args: {{
    variant: 'primary',
    size: 'md',
    children: 'Disabled',
    disabled: true,
  }},
}};
"""


def main():
    parser = argparse.ArgumentParser(description="从 Figma 生成 Storybook 故事")
    parser.add_argument("--figma-key", required=True, help="Figma file_key")
    parser.add_argument("--component-key", help="单个组件 key（不指定则用 --all）")
    parser.add_argument("--all", action="store_true", help="生成所有组件")
    parser.add_argument("--output", required=True, help="输出目录")
    args = parser.parse_args()

    list_components, get_nodes = _import_figma_client()

    if args.all:
        components = list_components(args.figma_key)
    elif args.component_key:
        components = [c for c in list_components(args.figma_key) if c.get("key") == args.component_key]
        if not components:
            sys.stderr.write(f"未找到组件 key={args.component_key}\n")
            sys.exit(1)
    else:
        sys.stderr.write("必须指定 --component-key 或 --all\n")
        sys.exit(1)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    results = []

    for comp in components:
        name = _to_pascal_case(comp.get("name", "Component"))
        description = comp.get("description", "")
        comp_dir = out / name
        comp_dir.mkdir(parents=True, exist_ok=True)
        # 写组件
        (comp_dir / f"{name}.tsx").write_text(
            generate_component_stub(name, description), encoding="utf-8"
        )
        # 写 story
        (comp_dir / f"{name}.stories.tsx").write_text(
            generate_story(name, description), encoding="utf-8"
        )
        # 写 index 导出
        (comp_dir / "index.ts").write_text(f"export * from './{name}';\n", encoding="utf-8")
        results.append({
            "component_key": comp.get("key"),
            "name": name,
            "files": [str(p) for p in [
                comp_dir / f"{name}.tsx",
                comp_dir / f"{name}.stories.tsx",
                comp_dir / "index.ts",
            ]],
        })
        sys.stderr.write(f"[sync] {name} → {comp_dir}/\n")

    print(json.dumps({
        "figma_key": args.figma_key,
        "output": str(out),
        "components": results,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
