#!/usr/bin/env python3
"""Render the email-safe edition: data/newsletter-email.html (global) and
per-user variants in data/emails/<slug>.html.

v4: the newsletter is a 500-700 word digest with inline links. The global
email carries the digest + the "By the numbers" charts + the full link
list. Each subscriber ALSO gets a "From your sources" section containing
ONLY their own scraped URLs — per-user scoping is enforced here (the
caller passes that user's items; nothing else is mixed in).

Email-safe means: table-based layout, inline CSS only, no webfonts, no
flexbox/grid, no external stylesheets, light theme, absolute URLs.
Chart PNGs are referenced at their hosted URLs
(https://aadit-field-manual.web.app/charts/<edition>/<id>.png) — the
pipeline writes the PNGs into web/public/charts/<edition>/ before this
runs, and the scheduled job deploys the site before sending.

Footer: "Reply to this email to unsubscribe" (manual handling for now —
no fake unsubscribe links).
"""
import html
import re
from pathlib import Path

SITE = "https://aadit-field-manual.web.app"

BG = "#fbfaf7"
INK = "#1d1a16"
MUTED = "#6f675c"
FAINT = "#a39a8c"
ACCENT = "#b0511f"
LINE = "#e9e2d6"


def _e(text):
    return html.escape(text or "", quote=True)


def md_to_email_html(md):
    """Minimal SAFE markdown -> HTML for the digest.

    Escapes everything first, then allows only: **bold**, [text](http...),
    ## subheads, and paragraphs. Anything else renders as plain text.
    """
    text = html.escape(md or "")
    # Inline formatting on the escaped text ([ ] ( ) * are not escaped).
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)

    def _link(m):
        label, url = m.group(1), m.group(2)
        return (f'<a href="{url}" style="color:{ACCENT};'
                f'text-decoration:underline;">{label}</a>')

    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", _link, text)
    blocks = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if para.startswith("## "):
            blocks.append(
                f'<h3 style="font-family:Georgia,serif;font-size:17px;'
                f'color:{INK};margin:18px 0 6px 0;">{para[3:].strip()}</h3>')
        else:
            inner = para.replace("\n", "<br>")
            blocks.append(
                f'<p style="font-size:14px;line-height:1.75;color:{INK};'
                f'margin:0 0 14px 0;">{inner}</p>')
    return "\n".join(blocks)


def _chart_rows(charts, edition_id):
    rows = ""
    for spec in charts:
        img_url = f"{SITE}/charts/{edition_id}/{spec['id']}.png"
        rows += f"""
      <tr><td style="padding:18px 0 6px 0;">
        <div style="font-family:Georgia,serif;font-size:17px;font-weight:bold;color:{INK};">{_e(spec['title'])}</div>
        <div style="font-size:12px;color:{MUTED};padding:2px 0 8px 0;">{_e(spec['subtitle'])}</div>
        <img src="{img_url}" alt="{_e(spec['title'])}" width="560" style="display:block;width:100%;max-width:560px;height:auto;border:1px solid {LINE};" />
        <div style="font-size:11px;color:{FAINT};padding-top:6px;">{_e(spec.get('note',''))}</div>
      </td></tr>"""
    return rows


def _links_rows(letter):
    rows = ""
    for section in letter["sections"]:
        items = "".join(
            f"""<tr><td style="padding:6px 0;border-top:1px solid {LINE};">
          <a href="{_e(it['url'])}" style="font-family:Georgia,serif;font-size:14px;font-weight:bold;color:{INK};text-decoration:none;">{_e(it['title'])}</a>
          <span style="font-size:11px;color:{FAINT};"> — {_e(it['source'])}</span>
        </td></tr>"""
            for it in section["items"])
        rows += f"""
      <tr><td style="padding:22px 0 4px 0;">
        <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:{ACCENT};font-weight:bold;">{_e(section['title'])}</div>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tbody>{items}</tbody></table>
      </td></tr>"""
    return rows


def _user_sources_rows(user_items):
    """'From your sources' — ONLY this subscriber's scraped URLs."""
    if not user_items:
        return ""
    items = ""
    for it in user_items:
        bullets = "".join(
            f"<li style=\"font-size:12px;color:{MUTED};margin:2px 0;\">{_e(b)}</li>"
            for b in (it.get("bullets") or [])[:3])
        bullets_html = f"<ul style=\"margin:6px 0 0 0;padding-left:18px;\">{bullets}</ul>" if bullets else ""
        items += f"""
        <tr><td style="padding:10px 0;border-top:1px solid {LINE};">
          <a href="{_e(it['url'])}" style="font-family:Georgia,serif;font-size:15px;font-weight:bold;color:{INK};text-decoration:none;">{_e(it.get('title') or it['url'])}</a>
          <div style="font-size:13px;color:{INK};padding-top:6px;line-height:1.6;">{_e(it.get('summary', ''))}</div>
          {bullets_html}
        </td></tr>"""
    return f"""
      <tr><td style="padding:26px 0 4px 0;">
        <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:{ACCENT};font-weight:bold;">Your sources</div>
        <h2 style="font-family:Georgia,serif;font-size:22px;color:{INK};margin:4px 0 8px 0;">From your sources</h2>
        <div style="font-size:13px;color:{MUTED};line-height:1.7;padding-bottom:6px;">You asked us to watch these — here's what they say.</div>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tbody>{items}</tbody></table>
      </td></tr>"""


def _footer(letter, pretty_date):
    return f"""
  <tr><td style="padding:30px 0 10px 0;border-top:1px solid {LINE};margin-top:20px;">
    <div style="font-size:12px;color:{MUTED};line-height:1.7;">
      You're getting this because you signed up for The Field Manual.<br>
      <a href="{SITE}" style="color:{ACCENT};">Read it on the web</a> &#183; Reply to this email to unsubscribe.
    </div>
    <div style="font-size:11px;color:{FAINT};padding-top:8px;">{letter['stats']['items']} stories &#183; {letter['stats']['sources']} sources &#183; filed {pretty_date}</div>
  </td></tr>"""


def _shell(title_line, sub_line, body_html):
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title_line)}</title></head>
<body style="margin:0;padding:0;background:{BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};"><tbody>
<tr><td align="center" style="padding:32px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;"><tbody>
  <tr><td style="padding-bottom:18px;border-bottom:1px solid {LINE};">
    <div style="font-family:Georgia,serif;font-size:24px;font-weight:bold;color:{INK};">The Field Manual</div>
    <div style="font-size:12px;color:{MUTED};padding-top:4px;">{_e(sub_line)}</div>
  </td></tr>
{body_html}
</tbody></table>
</td></tr>
</tbody></table>
</body></html>
"""


def render_email(letter, charts, edition_id):
    """The global email: digest + charts + full link list."""
    pretty_date = _pretty_date(letter["edition"])
    body = f"""
  <tr><td style="padding:20px 0 6px 0;">{md_to_email_html(letter['digest'])}</td></tr>
  <tr><td style="padding:8px 0 0 0;">
    <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:{ACCENT};font-weight:bold;padding-bottom:8px;">By the numbers</div>
  </td></tr>{_chart_rows(charts, edition_id)}
  <tr><td style="padding:8px 0 0 0;">
    <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:{ACCENT};font-weight:bold;padding-bottom:8px;">All the links</div>
  </td></tr>{_links_rows(letter)}
{_footer(letter, pretty_date)}"""
    return _shell(f"The Field Manual — {pretty_date}",
                  f"The last {letter['window_hours']} hours in {letter['word_count']} words · {pretty_date}",
                  body)


def render_user_email(letter, charts, edition_id, email, user_items):
    """Personalized email: global digest + ONLY this user's scraped URLs.

    ``user_items``: [{title, url, summary, bullets}] belonging to ``email``.
    Per-user scoping is the caller's contract — this function renders exactly
    what it is given.
    """
    pretty_date = _pretty_date(letter["edition"])
    body = f"""
  <tr><td style="padding:20px 0 6px 0;">{md_to_email_html(letter['digest'])}</td></tr>
{_user_sources_rows(user_items)}
  <tr><td style="padding:8px 0 0 0;">
    <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:{ACCENT};font-weight:bold;padding-bottom:8px;">By the numbers</div>
  </td></tr>{_chart_rows(charts, edition_id)}
  <tr><td style="padding:8px 0 0 0;">
    <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:{ACCENT};font-weight:bold;padding-bottom:8px;">All the links</div>
  </td></tr>{_links_rows(letter)}
{_footer(letter, pretty_date)}"""
    return _shell(f"The Field Manual — {pretty_date}",
                  f"The last {letter['window_hours']} hours in {letter['word_count']} words · {pretty_date}",
                  body)


def _pretty_date(edition):
    try:
        y, m, d = edition.split("-")
        months = ["January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November",
                  "December"]
        return f"{months[int(m)-1]} {int(d)}, {y}"
    except (ValueError, IndexError):
        return edition


def write_email(letter, charts, edition_id, out_dir=None):
    out_dir = Path(out_dir) if out_dir else Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    if "digest" not in letter:
        raise RuntimeError(
            "newsletter.json is not a v4 digest edition (no 'digest' key) — "
            "run 'services.manual edition' first")
    path = out_dir / "newsletter-email.html"
    path.write_text(render_email(letter, charts, edition_id), encoding="utf-8")
    return path
