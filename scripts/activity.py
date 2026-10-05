"""Render a 365-day activity heatmap using only Python's standard library."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

PALETTE = ("#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39")


def daily_activity(entries):
    """Count each problem at its stored submission date in UTC."""
    return Counter(
        datetime.fromtimestamp(info["submitted_at"], timezone.utc).date()
        for _, info in entries
    )


def activity_color(count):
    if count == 0:
        return PALETTE[0]
    if count == 1:
        return PALETTE[1]
    if count <= 3:
        return PALETTE[2]
    if count <= 5:
        return PALETTE[3]
    return PALETTE[4]


def heatmap_svg(entries, *, today=None):
    """Return SVG for exactly 365 dates, aligned to Monday–Sunday rows."""
    today = today if today is not None else datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    grid_start = start - timedelta(days=start.weekday())
    counts = daily_activity(entries)
    size, gap = 10, 3
    step = size + gap
    left, top = 36, 48
    columns = (today - grid_start).days // 7 + 1
    width, height = left + columns * step + 16, 174
    total = sum(count for day, count in counts.items() if start <= day <= today)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">',
        '<title id="title">LeetCode activity — last 365 days</title>',
        f'<desc id="description">{total} solved problems from {start} to {today}, in UTC. '
        'Columns are weeks and rows are Monday through Sunday.</desc>',
        '<g font-family="Arial, sans-serif" font-size="10" fill="#57606a">',
        f'<text x="{left}" y="14">{total} solved problems in the last 365 days · UTC</text>',
    ]
    for row, label in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
        parts.append(f'<text x="2" y="{top + row * step + 9}">{label}</text>')
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    for index in range(365):
        day = start + timedelta(days=index)
        column = (day - grid_start).days // 7
        x, y = left + column * step, top + day.weekday() * step
        if day.day == 1:
            parts.append(f'<text x="{x}" y="{top - 9}">{months[day.month - 1]}</text>')
        count = counts[day]
        noun = "problem" if count == 1 else "problems"
        parts.append(
            f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="2" '
            f'fill="{activity_color(count)}" data-date="{day}" data-count="{count}">'
            f'<title>{day}: {count} {noun} solved</title></rect>'
        )
    legend_x, legend_y = width - 146, 151
    parts.append(f'<text x="{legend_x - 28}" y="{legend_y + 9}">Less</text>')
    for index, color in enumerate(PALETTE):
        parts.append(
            f'<rect x="{legend_x + index * step}" y="{legend_y}" '
            f'width="{size}" height="{size}" rx="2" fill="{color}"/>'
        )
    parts.append(f'<text x="{legend_x + 5 * step + 4}" y="{legend_y + 9}">More</text>')
    parts.extend(["</g>", "</svg>"])
    return "\n".join(parts) + "\n"


def write_heatmap(entries, output=Path("assets/heatmap.svg"), *, today=None):
    output = Path(output)
    content = heatmap_svg(entries, today=today)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or output.read_text(encoding="utf-8") != content:
        output.write_text(content, encoding="utf-8")
    return content
