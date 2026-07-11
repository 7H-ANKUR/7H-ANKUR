#!/usr/bin/env python3
"""
Fallback contribution fetcher using only Python stdlib (urllib + html.parser).
Drop-in replacement for fetch_contributions.py when requests/bs4 aren't available.
Writes identical data/contributions.json output.
"""
import datetime
import json
import os
import re
import sys
import urllib.request
import html.parser

USERNAME = os.environ.get("GH_PROFILE_USER", "7H-ANKUR")
URL = f"https://github.com/users/{USERNAME}/contributions"
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "contributions.json")


class ContribParser(html.parser.HTMLParser):
    """Parse GitHub contribution calendar cells."""
    def __init__(self):
        super().__init__()
        self.days = []          # list of {date, count}
        self.tooltips = {}      # id -> text
        self._in_tooltip = False
        self._tooltip_id = None
        self._tooltip_text = []
        self._cell_ids = {}     # id -> date (for td.ContributionCalendar-day)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        # contribution day cell
        if tag == "td" and "ContributionCalendar-day" in attrs.get("class", ""):
            date = attrs.get("data-date")
            cell_id = attrs.get("id")
            if date and cell_id:
                self._cell_ids[cell_id] = date
        # tool-tip element
        if tag == "tool-tip":
            for_id = attrs.get("for", "")
            if for_id in self._cell_ids:
                self._in_tooltip = True
                self._tooltip_id = for_id
                self._tooltip_text = []

    def handle_data(self, data):
        if self._in_tooltip:
            self._tooltip_text.append(data)

    def handle_endtag(self, tag):
        if tag == "tool-tip" and self._in_tooltip:
            text = "".join(self._tooltip_text).strip()
            self.tooltips[self._tooltip_id] = text
            self._in_tooltip = False
            self._tooltip_id = None

    def build_days(self):
        days = []
        for cell_id, date in self._cell_ids.items():
            text = self.tooltips.get(cell_id, "")
            if re.search(r"no contributions", text, re.I):
                count = 0
            else:
                m = re.match(r"(\d+)", text)
                count = int(m.group(1)) if m else 0
            days.append({"date": date, "count": count})
        days.sort(key=lambda d: d["date"])
        return days


def fetch_days():
    req = urllib.request.Request(URL, headers={"User-Agent": "profile-readme-bot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html_text = resp.read().decode("utf-8", errors="replace")

    parser = ContribParser()
    parser.feed(html_text)
    days = parser.build_days()

    if not days:
        print("no calendar cells found -- github markup may have changed", file=sys.stderr)
        sys.exit(1)
    return days


def compute_current_streak(days):
    idx = len(days) - 1
    if days[idx]["count"] == 0:
        idx -= 1
    streak = 0
    end_idx = idx
    while idx >= 0 and days[idx]["count"] > 0:
        streak += 1
        idx -= 1
    start_idx = idx + 1
    if streak == 0:
        return 0, None, None
    return streak, days[start_idx]["date"], days[end_idx]["date"]


def compute_longest_streak(days):
    longest = run = 0
    longest_start = longest_end = None
    run_start_idx = None
    for i, d in enumerate(days):
        if d["count"] > 0:
            if run == 0:
                run_start_idx = i
            run += 1
            if run > longest:
                longest = run
                longest_start = days[run_start_idx]["date"]
                longest_end = days[i]["date"]
        else:
            run = 0
    return longest, longest_start, longest_end


def build_data(days):
    total = sum(d["count"] for d in days)
    active_days = sum(1 for d in days if d["count"] > 0)
    best = max(days, key=lambda d: d["count"])
    cur_len, cur_start, cur_end = compute_current_streak(days)
    long_len, long_start, long_end = compute_longest_streak(days)

    monthly = {}
    for d in days:
        key = d["date"][:7]
        monthly[key] = monthly.get(key, 0) + d["count"]
    monthly_list = [{"month": k, "total": v} for k, v in sorted(monthly.items())]

    return {
        "username": USERNAME,
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "range": {"start": days[0]["date"], "end": days[-1]["date"]},
        "total_contributions": total,
        "active_days": active_days,
        "avg_per_active_day": round(total / active_days, 1) if active_days else 0,
        "current_streak": {"length": cur_len, "start": cur_start, "end": cur_end},
        "longest_streak": {"length": long_len, "start": long_start, "end": long_end},
        "best_day": {"date": best["date"], "count": best["count"]},
        "monthly": monthly_list,
        "days": days,
    }


if __name__ == "__main__":
    print(f"Fetching contributions for {USERNAME} from {URL} ...")
    days = fetch_days()
    data = build_data(days)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"wrote {OUT_PATH}: {data['total_contributions']} contributions, "
          f"current streak {data['current_streak']['length']}, "
          f"longest streak {data['longest_streak']['length']}")
