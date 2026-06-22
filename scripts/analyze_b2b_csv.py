import csv, sys
from collections import Counter

csv_path = sys.argv[1] if len(sys.argv) > 1 else '/root/empire-v49/b2b_leads_export.csv'

niches = Counter()
states = Counter()
metros = Counter()
scores = []
total = 0
with open(csv_path) as f:
    reader = csv.DictReader(f)
    for row in reader:
        total += 1
        niche = row.get('SubNiche', '').strip()
        if niche:
            niches[niche[:60]] += 1
        state = row.get('State', '').strip().upper()[:2]
        if state:
            states[state] += 1
        metro = row.get('Metro', '').strip()
        if metro:
            metros[metro] += 1
        try:
            scores.append(int(row.get('Score', 0)))
        except:
            pass

print(f'Total rows: {total}')
print(f'\n=== SUB-NICHE DISTRIBUTION ===')
for niche, count in niches.most_common(30):
    print(f'  {count:5d}  {niche}')
print(f'\n  Total unique niches: {len(niches)}')
print(f'\n=== TOP STATES ===')
for state, count in states.most_common(10):
    print(f'  {count:5d}  {state}')
print(f'\n=== TOP METROS ===')
for metro, count in metros.most_common(12):
    print(f'  {count:5d}  {metro}')
print(f'\n=== SCORE DISTRIBUTION ===')
if scores:
    print(f'  Min: {min(scores)}, Max: {max(scores)}, Avg: {sum(scores)/len(scores):.0f}')
    print(f'  90+: {sum(1 for s in scores if s >= 90)}')
    print(f'  80-89: {sum(1 for s in scores if 80 <= s < 90)}')
    print(f'  <80: {sum(1 for s in scores if s < 80)}')
