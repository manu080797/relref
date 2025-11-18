#!/usr/bin/env python3
"""
mdfigs.py – Extract figures from Markdown, Quarto, and Pandoc documents.

Supports:
- Markdown inline figures:            ![alt](url "title")
- Markdown reference figures:         ![alt][id] + [id]: url "title"
- Quarto/Pandoc inline attributes:    ![alt](url){fig-cap="Caption" width=50%}
- Quarto/Pandoc block figures:

      ::: {.figure}
      ![alt](img.png)
      Caption text here
      :::

CLI:
    python mdfigs.py file.md
    python mdfigs.py file.md --json
"""

import re
import json
import argparse
from typing import List, Dict


class MarkdownFigureExtractor:
    INLINE_IMAGE_RE = re.compile(
        r'!\[([^\]]*)\]\(\s*([^\s\)]+)(?:\s+"([^"]*)")?\s*\)'
    )

    ATTR_BLOCK_RE = re.compile(
        r'\{([^}]*)\}'
    )

    REF_DEF_RE = re.compile(
        r'^\s*\[([^\]]+)\]:\s*(\S+)(?:\s+"([^"]*)")?\s*$'
    )

    REF_USE_RE = re.compile(
        r'!\[([^\]]*)\]\[([^\]]+)\]'
    )

    ATTR_PAIR_RE = re.compile(
        r'(\w[\w-]*)\s*=\s*"([^"]*)"|(\w[\w-]*)\s*=\s*([^\s]+)'
    )

    # Pandoc / Quarto block figure start: ::: {.figure}
    BLOCK_START_RE = re.compile(
        r'^\s*:::\s*\{?\.figure[^\}]*\}?\s*$'
    )
    BLOCK_END_RE = re.compile(r'^\s*:::\s*$')

    def __init__(self, markdown: str):
        self.markdown = markdown
        self.lines = markdown.splitlines()
        self.ref_defs: Dict[str, Dict[str, str]] = {}

    @classmethod
    def from_file(cls, path: str):
        with open(path, "r", encoding="utf-8") as f:
            return cls(f.read())

    def _find_reference_definitions(self):
        for line in self.lines:
            m = self.REF_DEF_RE.match(line)
            if m:
                ref_id = m.group(1)
                url = m.group(2)
                title = m.group(3) or ""
                self.ref_defs[ref_id] = {"url": url, "title": title}

    def _parse_attribute_block(self, attr_text: str) -> Dict[str, str]:
        attrs = {}
        for m in self.ATTR_PAIR_RE.finditer(attr_text):
            if m.group(1):
                attrs[m.group(1)] = m.group(2)
            else:
                attrs[m.group(3)] = m.group(4)
        return attrs

    def _extract_block_figure(self, start_index: int) -> Dict:
        """Extract a Quarto/Pandoc block figure starting at line start_index."""

        img = None
        caption_lines = []
        attributes = {}

        i = start_index + 1
        while i < len(self.lines):
            line = self.lines[i]

            # Block end
            if self.BLOCK_END_RE.match(line):
                break

            # Try to extract image in this block
            for m in self.INLINE_IMAGE_RE.finditer(line):
                alt = m.group(1)
                url = m.group(2)
                title = m.group(3) or ""

                # Look for attribute block after image
                attr_match = self.ATTR_BLOCK_RE.search(line[m.end():])
                if attr_match:
                    attributes.update(self._parse_attribute_block(attr_match.group(1)))

                img = {
                    "alt_text": alt,
                    "url": url,
                    "title": title,
                }
                # Continue to find caption lines below
            else:
                # If not an image line, treat as caption text
                caption_lines.append(line.strip())

            i += 1

        caption = "\n".join(l for l in caption_lines if l).strip()
        return {
            "type": "block",
            "syntax": "quarto/pandoc",
            "image": img,
            "caption": caption,
            "attributes": attributes,
            "start_line": start_index,
            "end_line": i,
            "raw": "\n".join(self.lines[start_index:i+1])
        }

    def extract_figures(self) -> List[Dict]:
        figures = []
        self._find_reference_definitions()

        i = 0
        while i < len(self.lines):
            line = self.lines[i]

            #--------------------------------------------------
            # 1) Block figures (Quarto or Pandoc)
            #--------------------------------------------------
            if self.BLOCK_START_RE.match(line):
                block_fig = self._extract_block_figure(i)
                if block_fig["image"] is not None:
                    figures.append(block_fig)
                i = block_fig["end_line"] + 1
                continue

            #--------------------------------------------------
            # 2) Inline Markdown / Quarto / Pandoc
            #--------------------------------------------------
            for m in self.INLINE_IMAGE_RE.finditer(line):
                alt = m.group(1)
                url = m.group(2)
                title = m.group(3) or ""

                attr_match = self.ATTR_BLOCK_RE.search(line[m.end():])
                attrs = {}
                if attr_match:
                    attrs = self._parse_attribute_block(attr_match.group(1))

                caption = (
                    attrs.get("fig-cap")
                    or attrs.get("caption")
                    or title
                    or alt
                )

                figures.append({
                    "type": "inline",
                    "syntax": "markdown/quarto/pandoc",
                    "alt_text": alt,
                    "url": url,
                    "title": title,
                    "caption": caption,
                    "attributes": attrs,
                    "line_no": i,
                    "raw": line.strip(),
                })

            #--------------------------------------------------
            # 3) Reference-style markdown images
            #--------------------------------------------------
            for m in self.REF_USE_RE.finditer(line):
                alt = m.group(1)
                ref_id = m.group(2)

                url = ""
                title = ""
                if ref_id in self.ref_defs:
                    url = self.ref_defs[ref_id]["url"]
                    title = self.ref_defs[ref_id]["title"]

                figures.append({
                    "type": "reference",
                    "syntax": "markdown",
                    "alt_text": alt,
                    "ref_id": ref_id,
                    "url": url,
                    "title": title,
                    "caption": title or alt,
                    "attributes": {},
                    "line_no": i,
                    "raw": line.strip(),
                })

            i += 1

        return figures


# ----------------------------------------------------------------------
# CLI SUPPORT
# ----------------------------------------------------------------------

def cli():
    parser = argparse.ArgumentParser(
        description="Extract figures from Markdown, Quarto, and Pandoc files."
    )
    parser.add_argument("input", help="Path to the markdown source file.")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    extractor = MarkdownFigureExtractor.from_file(args.input)
    figs = extractor.extract_figures()

    if args.json:
        print(json.dumps(figs, indent=2, ensure_ascii=False))
    else:
        print("\n=== FIGURES FOUND ===\n")
        for f in figs:
            print(f"- Type:     {f['type']}")
            print(f"  Syntax:   {f['syntax']}")
            if f["type"] == "block":
                print(f"  URL:      {f['image']['url']}")
                print(f"  Caption:  {f['caption']}")
            else:
                print(f"  URL:      {f['url']}")
                print(f"  Caption:  {f['caption']}")
            print(f"  Raw:      {f['raw']}\n")


if __name__ == "__main__":
    cli()
