#!/usr/bin/env python3
"""
Storybook 项目初始化器

在指定项目目录生成 .storybook/ 配置 + main.ts + preview.ts + 必要 scripts

用法：
  python3 init_storybook.py /path/to/project --output .storybook/
"""

import argparse
import json
import os
import sys
from pathlib import Path


STORYBOOK_MAIN = """/** @type {import('@storybook/react-vite').StorybookConfig} */
const config = {
  stories: ['../src/**/*.stories.@(ts|tsx|js|jsx)'],
  addons: [
    '@storybook/addon-links',
    '@storybook/addon-essentials',
    '@storybook/addon-a11y',
    '@storybook/addon-themes',
  ],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  docs: { autodocs: 'tag' },
  typescript: {
    check: false,
    reactDocgen: 'react-docgen-typescript',
  },
};
export default config;
"""

STORYBOOK_PREVIEW = """import type { Preview } from '@storybook/react';
import '../src/styles/globals.css';

const preview: Preview = {
  parameters: {
    actions: { argTypesRegex: '^on[A-Z].*' },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    backgrounds: {
      default: 'light',
      values: [
        { name: 'light', value: '#FFFFFF' },
        { name: 'dark', value: '#0A0A0A' },
      ],
    },
  },
};
export default preview;
"""

PACKAGE_SCRIPTS = {
    "storybook": "storybook dev -p 6006",
    "build-storybook": "storybook build",
    "chromatic": "npx chromatic --project-token $CHROMATIC_PROJECT_TOKEN",
}

NPM_DEPS = [
    "@storybook/react",
    "@storybook/react-vite",
    "@storybook/addon-links",
    "@storybook/addon-essentials",
    "@storybook/addon-a11y",
    "@storybook/addon-themes",
    "@storybook/blocks",
    "storybook",
    "chromatic",
]


def init_storybook(project_dir: str, output_dir: str) -> dict:
    """初始化项目 Storybook。"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 写 main.ts
    (out / "main.ts").write_text(STORYBOOK_MAIN, encoding="utf-8")
    # 写 preview.ts
    (out / "preview.ts").write_text(STORYBOOK_PREVIEW, encoding="utf-8")

    # 写 README
    readme = f"""# Storybook 配置

## 启动
```bash
npm run storybook   # 启动开发环境（http://localhost:6006）
npm run build-storybook   # 构建静态站点
npm run chromatic   # 跑视觉回归（需 CHROMATIC_PROJECT_TOKEN）
```

## 添加新组件
在 `src/{{ComponentName}}/{{ComponentName}}.stories.tsx` 写故事。

## 视觉回归
每次 push/PR 自动跑 Chromatic，截图对比。
"""
    (out / "README.md").write_text(readme, encoding="utf-8")

    # 更新 package.json
    pkg_path = Path(project_dir) / "package.json"
    if pkg_path.exists():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
            pkg.setdefault("scripts", {}).update(PACKAGE_SCRIPTS)
            # 写 devDependencies（仅追加不覆盖）
            dev_deps = pkg.setdefault("devDependencies", {})
            for dep in NPM_DEPS:
                if dep not in dev_deps:
                    dev_deps[dep] = "latest"
            pkg_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
            sys.stderr.write(f"[init] 已更新 {pkg_path}\n")
        except json.JSONDecodeError:
            sys.stderr.write(f"[init] 警告: {pkg_path} 解析失败，未更新\n")

    return {
        "output_dir": str(out),
        "files_created": [
            str(out / "main.ts"),
            str(out / "preview.ts"),
            str(out / "README.md"),
        ],
        "package_json_updated": pkg_path.exists(),
    }


def main():
    parser = argparse.ArgumentParser(description="Storybook 项目初始化")
    parser.add_argument("project_dir", help="项目目录")
    parser.add_argument("--output", default=".storybook", help="Storybook 配置输出目录")
    args = parser.parse_args()

    if not os.path.isdir(args.project_dir):
        sys.stderr.write(f"项目目录不存在: {args.project_dir}\n")
        sys.exit(1)

    result = init_storybook(args.project_dir, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
