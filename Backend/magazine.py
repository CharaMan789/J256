import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None


def _styles():
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=40, leading=48, alignment=TA_CENTER, spaceAfter=18,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", parent=base["Normal"], fontName="Helvetica", fontSize=13,
            leading=18, alignment=TA_CENTER, textColor=colors.HexColor("#555555"), spaceAfter=4,
        ),
        "toc_heading": ParagraphStyle(
            "toc_heading", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=13, spaceBefore=34, spaceAfter=10, alignment=TA_CENTER,
        ),
        "toc_item": ParagraphStyle(
            "toc_item", parent=base["Normal"], fontName="Times-Roman", fontSize=11,
            spaceAfter=6, textColor=colors.HexColor("#333333"), alignment=TA_CENTER,
        ),
        "article_title": ParagraphStyle(
            "article_title", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=22, leading=27, spaceAfter=6,
        ),
        "byline": ParagraphStyle(
            "byline", parent=base["Normal"], fontName="Helvetica-Oblique", fontSize=9.5,
            leading=13, textColor=colors.HexColor("#777777"), spaceAfter=16,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontName="Times-Roman", fontSize=11.5,
            leading=17, spaceAfter=10,
        ),
        "attachment_note": ParagraphStyle(
            "attachment_note", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=9, textColor=colors.HexColor("#888888"), spaceAfter=10,
        ),
    }


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Mirrors the syntax in frontend/formatting.js: **bold**, *italic*/_italic_,
# `code`, [font=Name]...[/font], $inline$, $$block$$. ReportLab Paragraphs
# accept a small subset of HTML-like tags (<b>, <i>, <font>), which bold,
# italic, and font map onto directly. ReportLab can't render actual LaTeX
# (no MathJax/KaTeX equivalent available here), so LaTeX expressions are
# rendered as their literal source in a monospace font instead of being
# silently dropped — the PDF reader still sees what the formula was meant
# to say, even if it isn't typeset.
def _format_inline(text: str) -> str:
    escaped = _escape(text)

    escaped = re.sub(
        r"\$\$([\s\S]+?)\$\$",
        lambda m: f'<font face="Courier">{m.group(1).strip()}</font>',
        escaped,
    )
    # Same "no leading/trailing space inside $...$" rule as formatting.js,
    # so a body with "$5 and $10" isn't misread as LaTeX here either.
    escaped = re.sub(
        r"\$(\S[^\n$]*?\S|\S)\$",
        lambda m: f'<font face="Courier">{m.group(1).strip()}</font>',
        escaped,
    )
    escaped = re.sub(
        r"\[font=([^\]\n]+)\]([\s\S]+?)\[/font\]",
        lambda m: f'<font face="{_pdf_font_name(m.group(1))}">{m.group(2)}</font>',
        escaped,
    )
    escaped = re.sub(r"\*\*([^\n*]+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(
        r"(?:\*([^\n*]+?)\*)|(?:_([^\n_]+?)_)",
        lambda m: f"<i>{m.group(1) or m.group(2)}</i>",
        escaped,
    )
    escaped = re.sub(r"`([^\n`]+?)`", r'<font face="Courier">\1</font>', escaped)
    return escaped


# The web font picker offers real webfont names (e.g. "Fraunces, serif")
# that ReportLab's built-in font table doesn't know. Map each option to
# the closest built-in ReportLab font rather than erroring on an unknown
# face — anything unrecognized just falls back to the body's own font.
_PDF_FONT_MAP = {
    "source serif 4, serif": "Times-Roman",
    "fraunces, serif": "Times-Bold",
    "inter, sans-serif": "Helvetica",
    "ibm plex mono, monospace": "Courier",
}


def _pdf_font_name(css_font_value: str) -> str:
    return _PDF_FONT_MAP.get(css_font_value.strip().lower(), "Times-Roman")


def build_magazine_pdf(posts: list[dict], upload_dir: Path) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=28 * mm, bottomMargin=22 * mm, leftMargin=24 * mm, rightMargin=24 * mm,
        title="J256 Magazine",
    )
    styles = _styles()
    story = []

    # --- Cover page ---
    story.append(Spacer(1, 55 * mm))
    story.append(Paragraph("J256", styles["cover_title"]))
    story.append(Paragraph("Campus Magazine — IISER TVM", styles["cover_sub"]))
    story.append(Paragraph(datetime.now().strftime("Compiled %d %B %Y"), styles["cover_sub"]))
    story.append(Paragraph(
        f"{len(posts)} article{'s' if len(posts) != 1 else ''} in this issue",
        styles["cover_sub"],
    ))

    if posts:
        story.append(Paragraph("In this issue", styles["toc_heading"]))
        for p in posts:
            story.append(Paragraph(f"{_escape(p['title'])} — {_escape(p['author'])}", styles["toc_item"]))

    # --- Articles ---
    for post in posts:
        story.append(PageBreak())
        story.append(Paragraph(_escape(post["title"]), styles["article_title"]))

        byline = _escape(post["author"])
        if post.get("is_anonymous"):
            byline += " (anonymous)"
        if post.get("published_at"):
            byline += f" · {post['published_at'][:10]}"
        story.append(Paragraph(byline, styles["byline"]))

        for para in post["body"].split("\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(_format_inline(para), styles["body"]))
            else:
                story.append(Spacer(1, 6))

        for att in post.get("attachments", []):
            if att["kind"] == "image":
                img_path = upload_dir / Path(att["url"]).name
                if img_path.exists():
                    try:
                        avail_width = doc.width
                        ratio = 0.6
                        if PILImage:
                            with PILImage.open(img_path) as im:
                                w, h = im.size
                            if w:
                                ratio = h / w
                        height = avail_width * ratio
                        max_height = doc.height * 0.75
                        if height > max_height:
                            height = max_height
                            avail_width = height / ratio if ratio else avail_width
                        story.append(Spacer(1, 10))
                        story.append(RLImage(str(img_path), width=avail_width, height=height))
                        story.append(Spacer(1, 10))
                    except Exception:
                        story.append(Paragraph(f"[image: {_escape(att['original_name'])}]", styles["attachment_note"]))
            else:
                story.append(Paragraph(
                    f"📎 {att['kind']}: {_escape(att['original_name'])} (available online)",
                    styles["attachment_note"],
                ))

    doc.build(story)
    return buffer.getvalue()