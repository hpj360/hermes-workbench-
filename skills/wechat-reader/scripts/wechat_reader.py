#!/usr/bin/env python3
"""微信文章提取器 - 带重试和多UA轮换"""
import requests
import re
import json
import sys
import time
import random
from bs4 import BeautifulSoup, NavigableString

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S908E) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 12; Redmi K50 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

ACCEPT_HEADERS = [
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
]

def get_article(url, max_retries=5):
    for attempt in range(max_retries):
        ua = random.choice(USER_AGENTS)
        accept = random.choice(ACCEPT_HEADERS)
        headers = {
            "User-Agent": ua,
            "Accept": accept,
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "no-cache",
        }
        try:
            time.sleep(random.uniform(1.0, 2.5))
            resp = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
            html_content = resp.text

            # 检查是否被拦截
            if "wappoc_appmsgcaptcha" in html_content or "环境异常" in html_content:
                print(f"  第{attempt+1}次尝试: 被验证码拦截，切换UA重试...", file=sys.stderr)
                continue

            # 检查是否有正文
            if "js_content" in html_content or "rich_media_content" in html_content:
                print(f"  第{attempt+1}次尝试: 成功获取正文!", file=sys.stderr)
                return html_content

            # 返回了HTML但不确定
            if len(html_content) > 5000:
                print(f"  第{attempt+1}次尝试: 获取到内容 (长度{len(html_content)})", file=sys.stderr)
                return html_content

            print(f"  第{attempt+1}次尝试: 返回内容过短 (长度{len(html_content)})，重试...", file=sys.stderr)

        except Exception as e:
            print(f"  第{attempt+1}次尝试: 网络错误 - {str(e)}", file=sys.stderr)
            time.sleep(2)

    print(f"⚠️  全部{max_retries}次尝试失败，请稍后再试或检查URL", file=sys.stderr)
    sys.exit(1)

def parse_article(html_content, url):
    result = {
        "url": url,
        "title": "",
        "author": "",
        "publish_time": "",
        "markdown": "",
        "content_text": "",
    }

    soup = BeautifulSoup(html_content, 'html.parser')

    # 提取标题
    for selector in ['h1.rich_media_title', 'h1#activity-name', '.rich_media_title', 'h1']:
        el = soup.select_one(selector) if '.' in selector or '#' in selector else soup.find(selector)
        if el and el.get_text(strip=True):
            result["title"] = el.get_text(strip=True)
            break

    if not result["title"]:
        title_match = re.search(r'var\s+msg_title\s*=\s*["\'](.+?)["\']', html_content)
        if title_match:
            result["title"] = title_match.group(1).strip()

    # 提取作者
    for selector in ['#js_name', '#meta_content .rich_media_meta_nickname', '.rich_media_meta_nickname', '.original_person']:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True):
            result["author"] = el.get_text(strip=True)
            break

    # 提取发布时间
    for selector in ['#publish_time', '.rich_media_meta_text em', '.rich_media_meta_text']:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True):
            result["publish_time"] = el.get_text(strip=True)
            break

    # 提取正文
    content = soup.find(id='js_content') or soup.find(class_='rich_media_content')
    if content:
        for tag in content.find_all(['script', 'style']):
            tag.decompose()
        result["content_text"] = content.get_text(separator='\n', strip=True)
        result["markdown"] = html_to_markdown(content)

    return result

def html_to_markdown(element, depth=0):
    if depth > 6:
        return element.get_text(strip=True) if element else ""

    md_parts = []
    for child in element.children:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                md_parts.append(text)
            continue

        tag_name = (child.name or '').lower()
        text = child.get_text(strip=True)

        if tag_name in ['h1', 'h2', 'h3']:
            md_parts.append(f"\n\n## {text}\n\n")
        elif tag_name in ['h4', 'h5', 'h6']:
            md_parts.append(f"\n\n### {text}\n\n")
        elif tag_name == 'p':
            inner = html_to_markdown(child, depth + 1)
            if inner.strip():
                md_parts.append(f"\n{inner.strip()}\n")
        elif tag_name == 'br':
            md_parts.append("\n")
        elif tag_name in ['strong', 'b']:
            md_parts.append(f"**{text}**")
        elif tag_name in ['em', 'i']:
            md_parts.append(f"*{text}*")
        elif tag_name in ['ul', 'ol']:
            for i, li in enumerate(child.find_all('li', recursive=False), 1):
                li_text = li.get_text(strip=True)
                bullet = f"{i}." if tag_name == 'ol' else "-"
                md_parts.append(f"{bullet} {li_text}\n")
            md_parts.append("\n")
        elif tag_name == 'blockquote':
            for line in text.split('\n'):
                if line.strip():
                    md_parts.append(f"> {line.strip()}\n")
            md_parts.append("\n")
        elif tag_name == 'a':
            href = child.get('href', '')
            if href:
                md_parts.append(f"[{text}]({href})")
            else:
                md_parts.append(text)
        elif tag_name in ['img']:
            alt = child.get('data-src') or child.get('src') or ''
            if alt:
                md_parts.append(f"\n![图片]({alt})\n")
        elif tag_name in ['section', 'div', 'span']:
            md_parts.append(html_to_markdown(child, depth + 1))
        elif text:
            md_parts.append(text)

    return re.sub(r'\n{4,}', '\n\n', ''.join(md_parts)).strip()

def main():
    if len(sys.argv) < 2:
        print("用法: python3 wechat_reader_v2.py <微信文章URL> [--json|--text]")
        sys.exit(1)

    url = sys.argv[1]
    fmt = "md"
    if "--json" in sys.argv:
        fmt = "json"
    elif "--text" in sys.argv:
        fmt = "text"

    print(f"正在获取文章: {url}", file=sys.stderr)
    html_content = get_article(url)
    article = parse_article(html_content, url)

    if not article["title"] and not article["content_text"]:
        print("⚠️ 无法解析文章内容，请检查 URL", file=sys.stderr)
        sys.exit(1)

    if fmt == "json":
        output = {
            "title": article["title"],
            "author": article["author"],
            "publish_time": article["publish_time"],
            "url": article["url"],
            "content_markdown": article["markdown"],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    elif fmt == "text":
        print(f"# {article['title']}")
        if article["author"]:
            print(f"作者: {article['author']}")
        if article["publish_time"]:
            print(f"发布时间: {article['publish_time']}")
        print(f"原文: {article['url']}")
        print("\n" + "=" * 50 + "\n")
        print(article["content_text"])
    else:
        print(f"# {article['title']}")
        if article["author"]:
            print(f"\n**作者**: {article['author']}")
        if article["publish_time"]:
            print(f"**发布时间**: {article['publish_time']}")
        print(f"\n**原文**: {article['url']}")
        print("\n" + "---" + "\n")
        print(article["markdown"])

if __name__ == "__main__":
    main()
