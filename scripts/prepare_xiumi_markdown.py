"""把最终 Markdown 整理成可直接推秀米的版本。

推秀米前必须解决三件事，否则会静默丢内容：

1. **内嵌 `data:` URL 图片会被秀米剥掉。** 样式保留模式只把「本地文件」图片粘贴
   转成 `img.xiumi.us` 的 CDN 地址；直接写进文本 comp 的 base64 在保存时会被
   秀米丢掉。所以这里把每个 `data:image/...;base64,...` 落成本地文件再改引用。

2. **相对路径会在渲染时失效。** 这里统一改写成绝对路径。

3. **路径里的下划线会被 Markdown 当成强调标记吃掉。** 上游产物里已经能看到
   `module_lib_20260927_0752` 变成了 `modulelib202609270752`（`_` 成对被当作
   斜体）。这类路径按字面找必然 404，所以这里做一次「去掉下划线后比对」的
   模糊匹配，把引用指回真实文件。

    python scripts/prepare_xiumi_markdown.py output/xxx/wanyou_combined.md
"""

import argparse
import base64
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

DATA_IMAGE_RE = re.compile(r"data:image/(?P<kind>[A-Za-z0-9.+-]+);base64,(?P<data>[A-Za-z0-9+/=\s]+)")
# Markdown 图片：![alt](src)，src 里不含括号与空白（我们自己的产物都满足）。
MD_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)\)")

EXT_BY_KIND = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "gif": "gif", "webp": "webp"}


def _normalize(path: str) -> str:
    """去下划线、统一分隔符、转小写：用来容忍被 Markdown 吃掉的 `_`。"""
    return path.replace("\\", "/").replace("_", "").lower()


# 建索引时跳过的目录：和图片无关，而且体量大。
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "selenium_cache"}


class AssetResolver:
    """把一个可能已经失真的图片引用解析成真实文件的绝对路径。"""

    def __init__(self, roots: list[pathlib.Path], index_root: pathlib.Path):
        self.roots = roots
        self.index_root = index_root
        self._index: dict[str, pathlib.Path] | None = None

    def _build_index(self) -> dict[str, pathlib.Path]:
        """索引键是「相对项目根、去掉下划线」的路径。

        引用里通常带 `output/` 前缀，所以索引必须以项目根为基准建，
        否则键对不上（`modulelib.../a.png` vs `output/modulelib.../a.png`）。
        """
        index: dict[str, pathlib.Path] = {}
        if not self.index_root.exists():
            return index
        for path in self.index_root.rglob("*"):
            if not path.is_file():
                continue
            parts = path.relative_to(self.index_root).parts
            if any(part in SKIP_DIRS for part in parts):
                continue
            index.setdefault(_normalize("/".join(parts)), path)
        return index

    def resolve(self, src: str) -> pathlib.Path | None:
        raw = src.strip().lstrip("./")
        if not raw:
            return None

        candidate = pathlib.Path(raw)
        # 先试：绝对路径 / 相对 Markdown 目录 / 相对项目根
        tries = [candidate] if candidate.is_absolute() else [root / raw for root in self.roots]
        for path in tries:
            if path.exists():
                return path.resolve()

        # 再试：去掉下划线后按索引匹配
        if self._index is None:
            self._index = self._build_index()
        return self._index.get(_normalize(raw))


def extract_data_images(text: str, image_dir: pathlib.Path) -> tuple[str, int]:
    """把内嵌 base64 图片写成文件，返回 (新文本, 落地张数)。"""
    image_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    def repl(match: re.Match) -> str:
        kind = match.group("kind").lower()
        ext = EXT_BY_KIND.get(kind, "png")
        payload = re.sub(r"\s+", "", match.group("data"))
        if payload in written:
            return written[payload]
        raw = base64.b64decode(payload)
        path = image_dir / f"img_{len(written) + 1:04d}.{ext}"
        path.write_bytes(raw)
        written[payload] = str(path)
        return str(path)

    return DATA_IMAGE_RE.sub(repl, text), len(written)


def rewrite_local_images(text: str, resolver: AssetResolver) -> tuple[str, list[str], list[str]]:
    """把本地图片引用改写成绝对路径。返回 (新文本, 修复的引用, 仍未找到的引用)。"""
    fixed: list[str] = []
    missing: list[str] = []

    def repl(match: re.Match) -> str:
        alt, src = match.group("alt"), match.group("src")
        if src.startswith(("http://", "https://", "data:")):
            return match.group(0)
        resolved = resolver.resolve(src)
        if resolved is None:
            missing.append(src)
            return match.group(0)
        if str(resolved) != src:
            fixed.append(f"{src} → {resolved}")
        return f"![{alt}]({resolved})"

    return MD_IMAGE_RE.sub(repl, text), fixed, missing


def main() -> int:
    parser = argparse.ArgumentParser(description="整理出可直接推秀米的 Markdown")
    parser.add_argument("markdown", help="最终 Markdown 路径")
    parser.add_argument("--output", default="", help="输出路径，默认 <stem>_xiumi.md")
    parser.add_argument("--image-dir", default="", help="内嵌图片落地目录，默认 <markdown 所在目录>/xiumi_images")
    parser.add_argument("--quiet", action="store_true", help="只打印汇总")
    args = parser.parse_args()

    source = pathlib.Path(args.markdown).resolve()
    if not source.exists():
        print(f"找不到 Markdown：{source}")
        return 1
    target = pathlib.Path(args.output).resolve() if args.output else source.with_name(source.stem + "_xiumi.md")
    image_dir = pathlib.Path(args.image_dir).resolve() if args.image_dir else source.parent / "xiumi_images"

    text = source.read_text(encoding="utf-8")
    text, extracted = extract_data_images(text, image_dir)
    resolver = AssetResolver(roots=[source.parent, ROOT], index_root=ROOT)
    text, fixed, missing = rewrite_local_images(text, resolver)
    target.write_text(text, encoding="utf-8")

    remaining = len(DATA_IMAGE_RE.findall(text))
    print(f"内嵌图片落地：{extracted} 张 → {image_dir}")
    print(f"路径改写：{len(fixed)} 处；仍找不到：{len(missing)} 张")
    print(f"残留 data:image：{remaining}（必须为 0）")
    if fixed and not args.quiet:
        for item in fixed:
            print(f"  ~ {item}")
    for item in missing:
        print(f"  ! 找不到：{item}")
    print(f"输出：{target}")
    return 1 if remaining or missing else 0


if __name__ == "__main__":
    sys.exit(main())
