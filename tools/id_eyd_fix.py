"""EYD pass on the Indonesian chapters (2026-10-05): reduplicated words get their hyphen (kira kira -> kira-kira),
plus a short glossary of awkward or untranslated terms. Prose only: fenced code, inline code, links and
shortcodes are left untouched. Prints every change count per file."""
import re, glob, sys
RED = 'benar rata alih masing kira abu diam apa sama putus hati coba pohon mana jari hari titik tempat tahun sisa piksel nama lama laki huruf citra blok batas baik bab mesin model'.split()
RED_RE = re.compile(r'\b(' + '|'.join(RED) + r') \1\b', re.I)
GLOSS = [  # (pattern, replacement) on prose only; reviewed one by one
    (r'\bModul Ubah\b', 'Modul Perubahan'), (r'\*\*Ubah\*\*', '**Perubahan**'),
    (r'\bTime series\b', 'Deret waktu'), (r'\btime series\b', 'deret waktu'),
    (r'\bBugnya\b', 'Galatnya'),
]
def fix_prose(t):
    n = 0
    def red(m):
        nonlocal n; n += 1; a, b = m.group(0).split(' '); return f'{a}-{b}'
    t = RED_RE.sub(red, t)
    for a, b in GLOSS:
        t, k = re.subn(a, b, t); n += k
    return t, n
tot = 0
for f in sorted(glob.glob('id/*.qmd')):
    s = open(f, encoding='utf-8').read(); out = []; n = 0; fence = False
    for line in s.split('\n'):
        if line.lstrip().startswith('```'): fence = not fence; out.append(line); continue
        if fence or line.lstrip().startswith(('{{<', '#|', '|')) and 'id=' in line: out.append(line); continue
        parts = re.split(r'(`[^`]*`|\]\([^)]*\)|\{[^}]*\}|<[^>]+>)', line)   # keep code, link targets, attrs, html
        for i in range(0, len(parts), 2):
            parts[i], k = fix_prose(parts[i]); n += k
        out.append(''.join(parts))
    if n and '--dry' not in sys.argv: open(f, 'w', encoding='utf-8').write('\n'.join(out))
    if n: print(f, n)
    tot += n
print('total', tot)
