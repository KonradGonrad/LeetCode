"""Count unique problems per local day from original LeetSync code commits."""

import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def daily_activity(git, code_extensions, timezone="Europe/Warsaw"):
    log = git(
        "-c", "core.quotepath=false", "log", "--reverse", "--no-merges",
        "--format=%H%x00%ct%x00%s", "--name-only", "--no-renames",
        "--diff-filter=AM", "--fixed-strings", "--grep=LeetSync", "--",
        "solutions", "Algorithm", "Database", "Pandas",
    ).stdout
    events = set()
    stamp, subject, paths = None, "", []

    def record():
        if stamp is None or not re.search(r"\bTime:", subject):
            return
        automated = set()
        solved = set()
        for name in paths:
            path = Path(name)
            problem = next((part for part in path.parts if re.fullmatch(r"\d+-.+", part)), None)
            if problem is None:
                continue
            if path.name in {".leetsync.json", "notes.md", "notes.ipynb"}:
                automated.add(problem)
            if path.suffix.lower() in code_extensions:
                solved.add(problem)
        day = datetime.fromtimestamp(stamp, ZoneInfo(timezone)).date()
        events.update((day, problem.split("-", 1)[1]) for problem in solved - automated)

    for line in log.splitlines():
        if "\0" in line:
            record()
            _, timestamp, subject = line.split("\0", 2)
            stamp, paths = int(timestamp), []
        elif line:
            paths.append(line)
    record()
    return dict(sorted(Counter(day for day, _ in events).items()))


def render_activity(counts, output, timezone="Europe/Warsaw"):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import dates, pyplot as plt, ticker

    today = datetime.now(ZoneInfo(timezone)).date()
    end = max(today, max(counts)) if counts else today
    start = min(counts) if counts else end - timedelta(days=29)
    days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    values = [counts.get(day, 0) for day in days]
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10}):
        fig, ax = plt.subplots(figsize=(12, 3.8), dpi=160)
        fig.set_facecolor("#0d1117")
        ax.set_facecolor("#0d1117")
        ax.bar(days, values, width=0.78, color="#3fb950", zorder=3)
        ax.set_title("Daily problem-solving activity", loc="left", color="#f0f6fc", pad=30, fontsize=16, weight="bold")
        ax.text(0, 1.04, f"{sum(values)} problem-days  ·  {len(counts)} active days  ·  {timezone}",
                transform=ax.transAxes, color="#8b949e", fontsize=10)
        ax.set_ylabel("Problems solved", color="#8b949e", labelpad=12)
        ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        locator = dates.AutoDateLocator(minticks=3, maxticks=8)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(dates.ConciseDateFormatter(locator))
        ax.tick_params(colors="#8b949e", length=0, pad=8)
        ax.xaxis.get_offset_text().set_color("#8b949e")
        ax.set_ylim(0, max(max(values, default=0) + 1, 2))
        ax.grid(axis="y", color="#21262d", zorder=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        if not counts:
            ax.text(.5, .5, "No LeetSync activity yet", transform=ax.transAxes,
                    ha="center", color="#8b949e")
        fig.tight_layout(pad=2)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, facecolor=fig.get_facecolor(), metadata={"Software": "LeetCode Notebook"})
        plt.close(fig)
