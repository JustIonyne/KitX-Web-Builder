"""Resolves the Bedrock creative-inventory layout (tabs -> groups/items) from the official id list.
Used by build_atlas.py; edit layout.py / groups.py to change what appears where."""
import re
from groups import GROUPS
import layout as L

COLOR_ORDER = ['white','light_gray','gray','black','brown','red','orange','yellow','lime','green','cyan','light_blue','blue','purple','magenta','pink']
WOOD_ORDER = ['oak','spruce','birch','jungle','acacia','dark_oak','mangrove','cherry','pale_oak','bamboo','crimson','warped','poplar']
MATERIALS = ['oak','spruce','birch','jungle','acacia','dark_oak','mangrove','cherry','pale_oak','bamboo_mosaic','bamboo','crimson','warped','poplar',
 'cobblestone','mossy_cobblestone','stone_brick','mossy_stone_brick','stone','smooth_stone','granite','polished_granite','diorite','polished_diorite','andesite','polished_andesite',
 'cobbled_deepslate','polished_deepslate','deepslate_brick','deepslate_tile','blackstone','polished_blackstone_brick','polished_blackstone','tuff_brick','polished_tuff','tuff',
 'sandstone','smooth_sandstone','cut_sandstone','red_sandstone','smooth_red_sandstone','cut_red_sandstone','brick','mud_brick','nether_brick','red_nether_brick','end_stone_brick','prismarine_brick','dark_prismarine','prismarine',
 'smooth_quartz','quartz','purpur','resin_brick','cinnabar','sulfur','copper','exposed','weathered','oxidized','waxed']
VARIANT_KIND = {'Potions':'potion','Splash Potions':'splash_potion','Lingering Potions':'lingering_potion','Beds':'bed','Banners':'banner','Arrows':'arrow'}
EXTRA = dict(L.EXTRA_GROUPS)
EXTRA['Dyes'] = None; EXTRA['Copper'] = None; EXTRA['Mob Eggs'] = None; EXTRA['Light Blocks'] = None
SPECIAL_RX = {
 'Dyes': re.compile(r'_dye$'),
 'Mob Eggs': re.compile(r'_spawn_egg$'),
 'Light Blocks': re.compile(r'^light_block_\d+$'),
 'Copper': re.compile(r'^(waxed_)?(exposed_|weathered_|oxidized_)?(copper_block|copper|cut_copper|chiseled_copper|copper_grate|copper_bulb)$'),
 'Ores': re.compile(r'_ore$'),
 'Logs': re.compile(r'_log$|_stem$|^bamboo_block$|^stripped_bamboo_block$'),
 'Woods': re.compile(r'_wood$|_hyphae$'),
 'Leaves': re.compile(r'_leaves$|^azalea_leaves_flowered$'),
 'Saplings': re.compile(r'_sapling$|^mangrove_propagule$'),
}
RULES = {t: rx for t, rx in GROUPS if rx is not None}
RULES.update(SPECIAL_RX)
ORDER_RULES = ['Hanging Signs','Boats with Chest']   # these must claim their ids before 'Signs' / 'Boats'

TOOL_ORDER = ['wooden','stone','copper','iron','golden','diamond','netherite']
ARMOR_ORDER = ['leather','chainmail','copper','iron','golden','diamond','netherite','turtle']
OXI = ['exposed_', 'weathered_', 'oxidized_']

def _oxi(i):
    j = i[6:] if i.startswith('waxed_') else i
    return (1 if i.startswith('waxed_') else 0, next((n + 1 for n, p in enumerate(OXI) if j.startswith(p)), 0))

def _key(title, i):
    ox = _oxi(i)
    if title in ('Swords','Spears','Axes','Pickaxes','Shovels','Hoes'):
        p = i.split('_')[0]; return (TOOL_ORDER.index(p) if p in TOOL_ORDER else 99, ox, i)
    if title in ('Helmets','Chestplates','Leggings','Boots','Nautilus Armor','Horse Armor'):
        p = i.split('_')[0]; return (ARMOR_ORDER.index(p) if p in ARMOR_ORDER else 99, ox, i)
    if title in ('Wool','Wool Carpet','Concrete','Concrete Powder','Terracotta','Glazed Terracottas','Shulker Boxes','Candles','Cushions','Dyes','Bundles','Harnesses','Glass','Glass Panes'):
        base = i.split('_')
        for n in (2, 1):
            c = '_'.join(base[:n])
            if c in COLOR_ORDER: return (COLOR_ORDER.index(c), ox, i)
        return (-1, ox, i)                  # undyed first
    j = 'oak_' + i[8:] if i.startswith('wooden_') else i
    if title in ('Planks','Fences','Fence Gates','Doors','Trapdoors','Buttons','Pressure Plates','Signs','Hanging Signs','Boats','Boats with Chest','Shelves'):
        for n in (2, 1):
            w = '_'.join(j.split('_')[:n])
            if w in WOOD_ORDER: return (WOOD_ORDER.index(w), ox, i)
        return (99, ox, i)                  # iron_door, nether_brick_fence ... after the wooden ones
    if i == 'iron_bars' or i == 'iron_chain': return (-1, ox, i)
    j2 = re.sub(r'^(waxed_)?(exposed_|weathered_|oxidized_)?', '', j)
    if title == 'Copper':
        types = ['copper_block','copper','cut_copper','chiseled_copper','copper_grate','copper_bulb']
        return (types.index(j2) if j2 in types else 99, ox, i)
    if title == 'Chests':
        base = {'chest':0,'trapped_chest':1,'ender_chest':2}
        return (base.get(i, 3), ox, i)
    if title == 'Lanterns':
        return (0 if i == 'lantern' else 1 if i == 'soul_lantern' else 2, ox, i)
    best, blen = 999, -1
    for r, t in enumerate(MATERIALS):       # most specific (longest) matching material wins
        if re.search(r'(^|_)%s(_|$)' % t, j2) and len(t) > blen: best, blen = r, len(t)
    return (best, ox, i)

def members_of(title, ids, variants):
    kind = VARIANT_KIND.get(title)
    if kind:
        m = []
        if kind == 'arrow' and 'arrow' in ids: m.append('arrow')
        m += [f'{v[0]}:{v[1]}' for v in variants if v[0] == kind]
        return m
    if title in EXTRA and EXTRA[title] is not None:
        return [i for i in EXTRA[title] if i in ids]
    rx = RULES.get(title)
    if rx is None: return []
    return sorted([i for i in ids if rx.search(i)], key=lambda i: _key(title, i))

def build_tabs(ids, variants):
    """ids: list of listed item ids; variants: [(id, aux, title, ...)]. -> (tabs, report)"""
    ids = list(ids); idset = set(ids)
    tabs_spec = [('Construction', L.CONSTRUCTION), ('Equipment', L.EQUIPMENT), ('Items', L.ITEMS), ('Nature', L.NATURE)]
    claimed = {}                       # id -> group title that claimed it (first group wins, in ORDER_RULES / layout order)
    gmem = {}
    titles = ORDER_RULES + [e[2:] for _, lst in tabs_spec for e in lst if e.startswith('G:') and e[2:] not in ORDER_RULES]
    for t in titles:
        if t in gmem: continue
        mem = []
        for mm in members_of(t, idset, variants):
            base = mm.split(':')[0]
            if base in claimed and ':' not in mm: continue       # already claimed by an earlier group
            mem.append(mm)
        for mm in mem:
            if ':' not in mm: claimed[mm] = t
        gmem[t] = mem
    placed = set(); tabs = []; warn = []
    for name, lst in tabs_spec:
        ent = []
        for e in lst:
            if e.startswith('G:'):
                t = e[2:]; mem = gmem.get(t, [])
                if not mem: warn.append(f'group {t!r} is empty'); continue
                if len(mem) == 1: ent.append(['i', mem[0]])
                else: ent.append(['g', t, mem])
                placed.update(m.split(':')[0] for m in mem)
            else:
                if e in idset and e not in placed and e not in claimed: ent.append(['i', e]); placed.add(e)
                elif e not in idset: warn.append(f'{name}: unknown id {e}')
        tabs.append({'n': name, 'e': ent})
    # anything not placed anywhere: put in the best-guess tab
    left = [i for i in ids if i not in placed and i not in claimed]
    claimed_unplaced = [i for i in claimed if i not in placed]
    guess = {'Construction': re.compile(r'_(block|bricks)$|^smooth_'), 'Equipment': re.compile(r'(armor|_on_a_stick|^cooked_)'), 'Nature': re.compile(r'(sapling|flower|mushroom|coral|ore$|grass|moss|leaves)')}
    extra = {n: [] for n, _ in tabs_spec}
    for i in left + claimed_unplaced:
        tab = next((n for n, rx in guess.items() if rx.search(i)), 'Items')
        extra[tab].append(i)
    for t in tabs:
        for i in extra[t['n']]: t['e'].append(['i', i])
    return tabs, {'warnings': warn, 'unplaced': {k: v for k, v in extra.items() if v}}
