"""Builds the creative-inventory tabs straight from the game's own creative content dump (creative_items.json):
groups (name, tab, icon) and items (group, order, aux). This is the authoritative layout; layout.py/groups.py are only
a fallback used when no dump is given."""
import json, re

TABS = [('Construction', 1), ('Equipment', 3), ('Items', 4), ('Nature', 2)]     # UI order; numbers are the dump's categories


def build_tabs_from_dump(path, lang, listed_ids, variants):
    d = json.load(open(path, encoding='utf-8'))
    groups, items = d['groups'], d['items']
    ids = set(listed_ids)
    vset = {(v[0], v[1]) for v in variants}
    vbases = {v[0] for v in variants}

    def key(name, aux):
        base = name.replace('minecraft:', '')
        if base not in ids:
            return None
        return f'{base}:{aux}' if (base, aux) in vset else base

    by_group = {}
    for x in items:
        by_group.setdefault(x['group_index'], []).append(x['item'])

    def title(g):
        n = g['name']
        t = lang.get(n)
        if t: return t
        return re.sub(r'([A-Z])', r' \1', n.replace('itemGroup.name.', '')).replace('_', ' ').strip().title()

    tabs, skipped, seen_titles = [], set(), {}
    for tab, cat in TABS:
        ent = []
        for gi, g in enumerate(groups):
            if g['category'] != cat:
                continue
            mem, seen = [], set()
            for it in by_group.get(gi, []):
                k = key(it['name'], it['aux_value'])
                if k is None:
                    skipped.add(it['name'].replace('minecraft:', '')); continue
                if k in seen: continue        # identical entries (e.g. 125 enchanted books differ only by NBT) collapse to one
                seen.add(k); mem.append(k)
            if not mem:
                continue
            if not g['name']:                 # unnamed group = a run of single, non-collapsed items
                ent += [['i', k] for k in mem]
            elif len(mem) == 1:
                ent.append(['i', mem[0]])
            else:
                ic = key(g['icon']['name'], g['icon']['aux_value'])
                ent.append(['g', title(g), mem, ic if ic in mem else mem[0]])
        tabs.append({'n': tab, 'e': ent})
    in_tabs = {k.split(':')[0] for t in tabs for e in t['e'] for k in ([e[1]] if e[0] == 'i' else e[2])}
    return tabs, {'not_in_our_list': sorted(skipped), 'search_only': sorted(ids - in_tabs)}
