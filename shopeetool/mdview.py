"""Hiển thị tài liệu Markdown đơn giản trong ô Text của Tkinter."""
import re
from tkinter import font as tkfont

_INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")


def _pick(root, candidates, default):
    fams = set(tkfont.families(root))
    for c in candidates:
        if c in fams:
            return c
    return default


def setup_tags(text):
    base = _pick(text, ("Segoe UI", "Arial", "DejaVu Sans", "Helvetica"), "TkDefaultFont")
    mono = _pick(text, ("Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Courier New"), "TkFixedFont")
    text.tag_configure("p", font=(base, 10), spacing1=2, spacing3=4)
    text.tag_configure("h1", font=(base, 18, "bold"), foreground="#0b3d91", spacing1=14, spacing3=6)
    text.tag_configure("h2", font=(base, 14, "bold"), foreground="#0b3d91", spacing1=12, spacing3=4)
    text.tag_configure("h3", font=(base, 11, "bold"), foreground="#1b5e20", spacing1=8, spacing3=2)
    text.tag_configure("b", font=(base, 10, "bold"))
    text.tag_configure("code", font=(mono, 10), background="#eceff4", foreground="#b71c1c")
    text.tag_configure("codeblock", font=(mono, 10), background="#f3f4f6", lmargin1=18, lmargin2=18,
                       spacing1=0, spacing3=0)
    text.tag_configure("li", font=(base, 10), lmargin1=18, lmargin2=36, spacing1=1, spacing3=2)
    text.tag_configure("li2", font=(base, 10), lmargin1=40, lmargin2=58, spacing1=1, spacing3=2)
    text.tag_configure("quote", font=(base, 10, "italic"), lmargin1=16, lmargin2=16, background="#fff8e1",
                       foreground="#5d4037", spacing1=2, spacing3=2)
    text.tag_configure("muted", font=(base, 9, "italic"), foreground="#777777", lmargin1=18, lmargin2=18)
    text.tag_configure("hr", foreground="#bbbbbb")
    text.tag_raise("b")      # chữ đậm/mã phải thắng font của danh sách, trích dẫn...
    text.tag_raise("code")


def _inline(text, s, tag):
    for part in _INLINE.split(s):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            text.insert("end", part[2:-2], (tag, "b"))
        elif part.startswith("`") and part.endswith("`"):
            text.insert("end", part[1:-1], (tag, "code"))
        else:
            text.insert("end", part, tag)


def _strip(s):
    return s.replace("**", "").replace("`", "")


def render(text, md):
    text.configure(state="normal")
    text.delete("1.0", "end")
    lines = md.splitlines()
    i, in_code = 0, False
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            in_code = not in_code
            i += 1
            continue
        if in_code:
            text.insert("end", line + "\n", "codeblock")
            i += 1
            continue
        if re.match(r"^\s*\|.*\|\s*$", line):
            block = []
            while i < len(lines) and re.match(r"^\s*\|.*\|\s*$", lines[i]):
                block.append(lines[i])
                i += 1
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in block]
            rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
            if rows:
                text.insert("end", "(" + "  |  ".join(_strip(c) for c in rows[0]) + ")\n", "muted")
                for r in rows[1:]:
                    text.insert("end", "• ", "li")
                    _inline(text, r[0], "li")
                    if len(r) > 1:
                        text.insert("end", "  —  ", "li")
                        _inline(text, "  —  ".join(r[1:]), "li")
                    text.insert("end", "\n", "li")
                text.insert("end", "\n", "p")
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            _inline(text, m.group(2), "h%d" % len(m.group(1)))
            text.insert("end", "\n", "p")
        elif re.match(r"^(\s*)[-*]\s+(.*)", line):
            m = re.match(r"^(\s*)[-*]\s+(.*)", line)
            tag = "li2" if len(m.group(1)) >= 2 else "li"
            text.insert("end", "• ", tag)
            _inline(text, m.group(2), tag)
            text.insert("end", "\n", tag)
        elif re.match(r"^(\s*)(\d+)\.\s+(.*)", line):
            m = re.match(r"^(\s*)(\d+)\.\s+(.*)", line)
            tag = "li2" if len(m.group(1)) >= 2 else "li"
            text.insert("end", m.group(2) + ". ", tag)
            _inline(text, m.group(3), tag)
            text.insert("end", "\n", tag)
        elif line.startswith(">"):
            _inline(text, line.lstrip("> ").rstrip(), "quote")
            text.insert("end", "\n", "quote")
        elif line.strip() in ("---", "***", "___"):
            text.insert("end", "─" * 70 + "\n", "hr")
        elif not line.strip():
            text.insert("end", "\n", "p")
        else:
            _inline(text, line, "p")
            text.insert("end", "\n", "p")
        i += 1
    text.configure(state="disabled")
    text.yview_moveto(0)
