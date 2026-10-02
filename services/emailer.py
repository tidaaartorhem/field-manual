#!/usr/bin/env python3
"""Render the email-safe edition: data/newsletter-email.html.

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


def render_email(letter, charts, edition_id):
    edition = letter["edition"]
    pretty_date = _pretty_date(edition)

    chart_imgs = ""
    for spec in charts:
        img_url = f"{SITE}/charts/{edition_id}/{spec['id']}.png"
        chart_imgs += f"""
      <tr><td style="padding:18px 0 6px 0;">
        <div style="font-family:Georgia,serif;font-size:17px;font-weight:bold;color:{INK};">{_e(spec['title'])}</div>
        <div style="font-size:12px;color:{MUTED};padding:2px 0 8px 0;">{_e(spec['subtitle'])}</div>
        <img src="{img_url}" alt="{_e(spec['title'])}" width="560" style="display:block;width:100%;max-width:560px;height:auto;border:1px solid {LINE};" />
        <div style="font-size:11px;color:{FAINT};padding-top:6px;">{_e(spec.get('note',''))}</div>
      </td></tr>"""

    sections_html = ""
    for section in letter["sections"]:
        items_html = ""
        for it in section["items"][:6]:
            b = it["briefing"]
            pub = f" &#183; {it['published']}" if it.get("published") else ""
            items_html += f"""
        <tr><td style="padding:10px 0;border-top:1px solid {LINE};">
          <a href="{_e(it['url'])}" style="font-family:Georgia,serif;font-size:15px;font-weight:bold;color:{INK};text-decoration:none;">{_e(it['title'])}</a>
          <div style="font-size:11px;color:{FAINT};padding-top:2px;">{_e(it['source'])}{pub}</div>
          <div style="font-size:13px;color:{INK};padding-top:6px;line-height:1.6;">{_e(b['lede'])}</div>
          <div style="font-size:12px;color:{MUTED};padding-top:4px;"><em>Why it matters:</em> {_e(b['why_it_matters'])}</div>
        </td></tr>"""
        sections_html += f"""
      <tr><td style="padding:26px 0 4px 0;">
        <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:{ACCENT};font-weight:bold;">{_e(section['kicker'])}</div>
        <h2 style="font-family:Georgia,serif;font-size:22px;color:{INK};margin:4px 0 8px 0;">{_e(section['title'])}</h2>
        <div style="font-size:13px;color:{INK};line-height:1.7;">{_e(section['narrative'])}</div>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tbody>{items_html}</tbody></table>
        <div style="margin-top:12px;padding:10px 14px;border-left:3px solid {ACCENT};background:#fdf6ef;font-size:13px;color:{INK};"><strong>So what?</strong> {_e(section['closing_take'])}</div>
      </td></tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Field Manual — {pretty_date}</title></head>
<body style="margin:0;padding:0;background:{BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};"><tbody>
<tr><td align="center" style="padding:32px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;"><tbody>
  <tr><td style="padding-bottom:18px;border-bottom:1px solid {LINE};">
    <div style="font-family:Georgia,serif;font-size:24px;font-weight:bold;color:{INK};">The Field Manual</div>
    <div style="font-size:12px;color:{MUTED};padding-top:4px;">The last {letter['window_hours']} hours in agentic AI &#183; {pretty_date}</div>
  </td></tr>
  <tr><td style="padding:20px 0 6px 0;font-family:Georgia,serif;font-size:16px;line-height:1.7;color:{INK};">{_e(letter['lede'])}</td></tr>
  <tr><td style="padding:8px 0 0 0;">
    <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:{ACCENT};font-weight:bold;padding-bottom:8px;">By the numbers</div>
  </td></tr>{chart_imgs}
  {sections_html}
  <tr><td style="padding:30px 0 10px 0;border-top:1px solid {LINE};margin-top:20px;">
    <div style="font-size:12px;color:{MUTED};line-height:1.7;">
      You're getting this because you signed up for The Field Manual.<br>
      <a href="{SITE}" style="color:{ACCENT};">Read it on the web</a> &#183; Reply to this email to unsubscribe.
    </div>
    <div style="font-size:11px;color:{FAINT};padding-top:8px;">{letter['stats']['items']} stories &#183; {letter['stats']['sources']} sources &#183; filed {pretty_date}</div>
  </td></tr>
</tbody></table>
</td></tr>
</tbody></table>
</body></html>
"""


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
    path = out_dir / "newsletter-email.html"
    path.write_text(render_email(letter, charts, edition_id), encoding="utf-8")
    return path
