"""Render aggregate GitHub statistics; never publish private repository details."""
import argparse
from collections import Counter
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo


def query_github(query):
    import json
    result = subprocess.run(['gh', 'api', 'graphql', '-f', f'query={query}'],
                            check=True, capture_output=True, text=True)
    response = json.loads(result.stdout)
    if response.get('errors'):
        raise RuntimeError('GitHub returned incomplete data; keeping previous metrics')
    return response['data']['user']


def collect():
    user = query_github('''query { user(login: "Kaffan9441") {
      contributionsCollection { contributionCalendar {
        totalContributions weeks { contributionDays { date contributionCount } }
      } }
      repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER, isFork: false) {
        pageInfo { hasNextPage }
        nodes { stargazerCount languages(first: 100, orderBy: {field: SIZE, direction: DESC}) {
          edges {size node {name color}}
        } }
      }
    } }''')
    if user['repositories']['pageInfo']['hasNextPage']:
        raise RuntimeError('Repository pagination required; keeping previous metrics')
    return user


def render(user, now):
    calendar = user['contributionsCollection']['contributionCalendar']
    days = sorted((d for w in calendar['weeks'] for d in w['contributionDays']), key=lambda d: d['date'])
    counts = {d['date']: d['contributionCount'] for d in days}
    best = streak = 0
    previous = None
    for day in days:
        date = datetime.strptime(day['date'], '%Y-%m-%d').date()
        if previous is not None and date != previous + timedelta(days=1):
            streak = 0
        streak = streak + 1 if day['contributionCount'] else 0
        best = max(best, streak)
        previous = date
    current = 0
    cursor = now.date()
    if not counts.get(cursor.isoformat(), 0):
        cursor -= timedelta(days=1)
    while counts.get(cursor.isoformat(), 0):
        current += 1
        cursor -= timedelta(days=1)
    repos = user['repositories']['nodes']
    languages, colors = Counter(), {}
    for repo in repos:
        for edge in repo['languages']['edges']:
            name = edge['node']['name']
            languages[name] += edge['size']
            colors[name] = edge['node']['color'] or '#9b2335'
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="390" viewBox="0 0 900 390" role="img" aria-labelledby="title desc">',
             '<title id="title">GitHub activity and public repository languages</title>',
             '<desc id="desc">Contribution counts and streaks for the last year, plus languages by bytes across public, non-fork repositories.</desc>',
             '<rect x="1" y="1" width="898" height="388" rx="16" fill="#0d1117" stroke="#30363d"/>',
             '<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif">']
    def text(x, y, value, size=14, color='#919ba7', weight=400):
        parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}">{escape(str(value))}</text>')
    text(28, 38, 'GITHUB ACTIVITY', 16, '#f7c9cc', 700)
    text(28, 62, f'Last year · {days[0]["date"]} to {days[-1]["date"]}', 12)
    stats = [(calendar['totalContributions'], 'Contributions'), (current, 'Current streak · days'),
             (best, 'Best streak · days'), (len(repos), 'Public original repos')]
    for i, (value, label) in enumerate(stats):
        x = 28 + 222 * i
        text(x, 116, f'{value:,}', 34, '#f0f6fc', 700)
        text(x, 144, label, 13)
    parts.append('<path d="M28 167H872" stroke="#30363d"/>')
    text(28, 196, 'LANGUAGES IN PUBLIC REPOSITORIES', 14, '#f7c9cc', 700)
    total_bytes = sum(languages.values())
    top = languages.most_common(5)
    if total_bytes:
        segments = top + ([('Other', total_bytes - sum(v for _, v in top))] if len(languages) > 5 else [])
        x = 28.0
        for name, size in segments:
            width = 844 * size / total_bytes
            parts.append(f'<rect x="{x:.2f}" y="214" width="{width:.2f}" height="12" fill="{colors.get(name, "#6e7681")}"/>')
            x += width
        for i, (name, size) in enumerate(segments):
            x, y = 28 + (i % 3) * 282, 254 + (i // 3) * 27
            parts.append(f'<circle cx="{x+5}" cy="{y-4}" r="5" fill="{colors.get(name, "#6e7681")}"/>')
            text(x + 17, y, f'{name} {size / total_bytes:.1%}', 13, '#c9d1d9')
    else:
        text(28, 246, 'No language data available yet.')
    text(28, 324, 'Counts follow GitHub contribution visibility; private repository details stay hidden.', 12)
    text(28, 350, f'Updated {now:%Y-%m-%d %H:%M %Z} · Refreshes daily', 12)
    text(28, 372, 'Languages measure code volume, not proficiency. Forks are excluded.', 11)
    parts.append('</g></svg>')
    return '\n'.join(parts) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('.generated/metrics.svg'))
    args = parser.parse_args()
    svg = render(collect(), datetime.now(ZoneInfo('America/Toronto')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg)
    print(f'Updated {args.output}')
