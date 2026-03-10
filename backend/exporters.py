"""
exporters.py  —  Markdown and HTML export from pipeline JSON
============================================================
DOCX is handled separately by build_doc.js (Node/docx library).
"""
from pathlib import Path


# ── SHARED ────────────────────────────────────────────────────────────────────

def _y_top(unit):
    bb = unit.get("bbox", [])
    if isinstance(bb, list) and len(bb) >= 2:
        try: return float(bb[1])
        except: pass
    if isinstance(bb, dict):
        try: return float(bb.get("y1", 0))
        except: pass
    return float("inf")

def _x_left(unit):
    bb = unit.get("bbox", [])
    if isinstance(bb, list) and len(bb) >= 1:
        try: return float(bb[0])
        except: pass
    if isinstance(bb, dict):
        try: return float(bb.get("x1", 0))
        except: pass
    return float("inf")

def _sort_yx(blocks):
    return sorted(blocks, key=lambda u: (_y_top(u), _x_left(u)))

def _split_runs(units):
    """Split reading_order into mode-1 (full) and mode-2 (left/right) runs."""
    runs, i = [], 0
    while i < len(units):
        kind = (units[i].get("kind") or "full").lower()
        if kind == "full":
            runs.append({"mode": 1, "blocks": [units[i]]})
            i += 1
        else:
            run = []
            while i < len(units):
                k = (units[i].get("kind") or "full").lower()
                if k not in ("left", "right"):
                    break
                run.append(units[i])
                i += 1
            runs.append({"mode": 2, "blocks": run})
    return runs

def _ordered_blocks(run):
    """For a run, return blocks in reading order: left top→bottom, then right top→bottom."""
    if run["mode"] == 1:
        return run["blocks"]
    blocks = run["blocks"]
    left  = _sort_yx([b for b in blocks if (b.get("kind") or "").lower() == "left"])
    right = _sort_yx([b for b in blocks if (b.get("kind") or "").lower() == "right"])
    return left + right


# ── MARKDOWN ──────────────────────────────────────────────────────────────────

def export_markdown(data: dict, out_path: Path):
    image = data.get("image", "Document")
    stem  = Path(image).stem if image else "Document"
    lines = [f"# {stem}", ""]

    units = data.get("reading_order", [])
    runs  = _split_runs(units)

    for run in runs:
        if run["mode"] == 2:
            blocks = run["blocks"]
            left  = _sort_yx([b for b in blocks if (b.get("kind") or "").lower() == "left"])
            right = _sort_yx([b for b in blocks if (b.get("kind") or "").lower() == "right"])

            if left:
                lines.append("<!-- left column -->")
            for unit in left:
                lines += _unit_to_md(unit)

            if right:
                lines.append("")
                lines.append("<!-- right column -->")
            for unit in right:
                lines += _unit_to_md(unit)
        else:
            for unit in run["blocks"]:
                lines += _unit_to_md(unit)

    out_path.write_text("\n".join(lines), encoding="utf-8")


def _unit_to_md(unit):
    t    = (unit.get("type") or "text").lower()
    text = (unit.get("text") or "").strip()
    out  = []

    if t == "table":
        matrix = (unit.get("table") or {}).get("matrix", [])
        if matrix:
            n_cols = max(len(r) for r in matrix)
            if n_cols >= 1:
                hdr = list(matrix[0]) + [""] * (n_cols - len(matrix[0]))
                out.append("| " + " | ".join(str(c) for c in hdr) + " |")
                out.append("| " + " | ".join(["---"] * n_cols) + " |")
                for row in matrix[1:]:
                    row = list(row) + [""] * (n_cols - len(row))
                    out.append("| " + " | ".join(str(c) for c in row) + " |")
                out.append("")
    elif t == "title":
        if text:
            out.append(f"## {text}")
            out.append("")
    elif t == "reference":
        if text:
            for line in text.split("\n"):
                if line.strip():
                    out.append(f"> {line}")
            out.append("")
    else:
        if text:
            for line in text.split("\n"):
                if line.strip():
                    out.append(line)
            out.append("")

    return out


# ── HTML ──────────────────────────────────────────────────────────────────────

def export_html(data: dict, out_path: Path):
    image = data.get("image", "Document")
    stem  = Path(image).stem if image else "Document"

    def esc(s):
        return (str(s)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    def unit_html(unit):
        t    = (unit.get("type") or "text").lower()
        text = (unit.get("text") or "").strip()
        parts = []

        if t == "table":
            matrix = (unit.get("table") or {}).get("matrix", [])
            if matrix:
                n_cols = max(len(r) for r in matrix)
                parts.append("<table>")
                for ri, row in enumerate(matrix):
                    row = list(row) + [""] * (n_cols - len(row))
                    is_hdr = ri < 2
                    tag    = "th" if is_hdr else "td"
                    cls    = ' class="hdr"' if is_hdr else (' class="alt"' if ri % 2 == 1 else "")
                    parts.append(f"<tr{cls}>")
                    for cell in row:
                        parts.append(f"<{tag}>{esc(cell)}</{tag}>")
                    parts.append("</tr>")
                parts.append("</table>")
        elif t == "title":
            if text:
                parts.append(f"<h2>{esc(text)}</h2>")
        elif t == "reference":
            if text:
                inner = "<br>".join(esc(l) for l in text.split("\n"))
                parts.append(f'<p class="ref">{inner}</p>')
        else:
            if text:
                inner = "<br>".join(esc(l) for l in text.split("\n"))
                parts.append(f"<p>{inner}</p>")

        return "\n".join(parts)

    units = data.get("reading_order", [])
    runs  = _split_runs(units)
    body  = []

    for run in runs:
        if run["mode"] == 2:
            blocks = run["blocks"]
            left  = _sort_yx([b for b in blocks if (b.get("kind") or "").lower() == "left"])
            right = _sort_yx([b for b in blocks if (b.get("kind") or "").lower() == "right"])

            left_html  = "\n".join(unit_html(u) for u in left)
            right_html = "\n".join(unit_html(u) for u in right)
            body.append(
                f'<div class="two-col">'
                f'<div class="col left-col">{left_html}</div>'
                f'<div class="col right-col">{right_html}</div>'
                f'</div>'
            )
        else:
            for unit in run["blocks"]:
                body.append(f'<div class="full">{unit_html(unit)}</div>')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{esc(stem)}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body  {{ font-family: "Times New Roman", serif; font-size: 11pt; line-height: 1.6;
           max-width: 960px; margin: 2rem auto; padding: 0 1.5rem; color: #111; background: #fff; }}
  h1    {{ font-size: 18pt; text-align: center; margin-bottom: 1.5rem; }}
  h2    {{ font-size: 13pt; margin: 1.2rem 0 0.4rem; color: #2E5594; }}
  p     {{ margin: 0.4rem 0; }}
  p.ref {{ font-style: italic; font-size: 9pt; color: #555; margin: 0.2rem 0; }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin: 0.8rem 0; }}
  .col  {{ min-width: 0; }}
  .full {{ margin: 0.5rem 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 0.8rem 0; font-size: 9.5pt; }}
  th, td {{ border: 1px solid #8EA9C1; padding: 4px 8px; text-align: left; }}
  tr.hdr th {{ background: #D9E1F2; font-weight: bold; }}
  tr.alt td {{ background: #F2F5FB; }}
  @media print {{
    .two-col {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<h1>{esc(stem)}</h1>
{"".join(body)}
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")