#!/usr/bin/env python3
"""
KitX Web Builder - Bedrock item id  ->  Java model / texture mapper.

Reads:
  * the Java assets folder        (assets/minecraft/{items,models,textures})
  * the Bedrock id list           (the DATA table inside KitX Web Builder index.html)
  * optionally the addon's item_icons.js (Bedrock id -> Bedrock texture path)

Writes (to --out):
  * bedrock_to_java_map.json   one entry per Bedrock id
  * java_models_resolved.json  every referenced Java model, parents flattened
  * mapping_report.md          what matched how, and everything that needs a human decision

Usage:
  python build_item_map.py --java "<...>/assets/minecraft" --html index.html \
      [--icons item_icons.js] [--out out_dir]
"""
import argparse, json, os, re, sys, collections

# --------------------------------------------------------------------------
# Manual tables (Bedrock name  ->  Java name). Everything else is automatic.
# --------------------------------------------------------------------------

# Used even when an identical Java name exists, because the meaning differs.
OVERRIDE_ITEM = {
    "snow": "snow_block",            # Bedrock `snow` = full block, Java `snow` = layer
    "nether_brick": "nether_bricks", # Bedrock `nether_brick` = block, Java `nether_brick` = ingot
}

# Bedrock legacy / renamed ids -> Java item id
ALIAS_ITEM = {
    "brick_block": "bricks", "web": "cobweb", "deadbush": "dead_bush", "tallgrass": "short_grass",
    "waterlily": "lily_pad", "noteblock": "note_block", "mob_spawner": "spawner", "melon_block": "melon",
    "magma": "magma_block", "quartz_ore": "nether_quartz_ore", "netherbrick": "nether_brick",
    "red_nether_brick": "red_nether_bricks", "end_bricks": "end_stone_bricks",
    "end_brick_stairs": "end_stone_brick_stairs", "hardened_clay": "terracotta", "lit_pumpkin": "jack_o_lantern",
    "grass_path": "dirt_path", "golden_rail": "powered_rail", "snow_layer": "snow",
    "stonecutter_block": "stonecutter", "slime": "slime_block",
    "fence": "oak_fence", "fence_gate": "oak_fence_gate", "trapdoor": "oak_trapdoor", "wooden_door": "oak_door",
    "wooden_button": "oak_button", "wooden_pressure_plate": "oak_pressure_plate", "wooden_slab": "oak_slab",
    "boat": "oak_boat", "boat_dark_oak": "dark_oak_boat",
    "normal_stone_slab": "stone_slab", "normal_stone_stairs": "stone_stairs",
    "chain": "iron_chain", "cave_vines": "glow_berries", "redstone_wire": "redstone",
    "powder_snow": "powder_snow_bucket", "scute": "turtle_scute", "undyed_shulker_box": "shulker_box",
    "villagebell": "bell", "banner": "white_banner", "banner_pattern": "creeper_banner_pattern",
    "exposed_copper_block": "exposed_copper", "weathered_copper_block": "weathered_copper",
    "oxidized_copper_block": "oxidized_copper", "waxed_copper": "waxed_copper_block",
    "waxed_exposed_copper_block": "waxed_exposed_copper", "waxed_weathered_copper_block": "waxed_weathered_copper",
    "waxed_oxidized_copper_block": "waxed_oxidized_copper",
    "compass_atlas": "compass", "lodestone_compass": "compass", "lodestonecompass_atlas": "compass",
    "watch_atlas": "clock", "recovery_compass_atlas": "recovery_compass",
    "map_locked": "filled_map", "empty_map": "map",
    "wolf_armor_dyed": "wolf_armor", "bucket_sulfur_cube": "sulfur_cube_bucket",
    "spawn_egg_sulfur_cube": "sulfur_cube_spawn_egg", "zombie_pigman_spawn_egg": "zombified_piglin_spawn_egg",
    "tropicalfish_spawn_egg": "tropical_fish_spawn_egg",
    "hoglin_meat_cooked": "cooked_porkchop", "hoglin_meat_raw": "porkchop",  # low confidence, see note
    "light_block_0": "light",
    # official Bedrock names (mojang-items.json) that differ from Java
    "azalea_leaves_flowered": "flowering_azalea_leaves", "dirt_with_roots": "rooted_dirt", "frame": "item_frame",
    "glow_frame": "glow_item_frame", "frog_spawn": "frogspawn", "prismarine_bricks_stairs": "prismarine_brick_stairs",
    "silver_glazed_terracotta": "light_gray_glazed_terracotta", "small_dripleaf_block": "small_dripleaf",
    "bed": "white_bed",
}
# Bedrock id -> Java *model* path (no Java item of its own)
ALIAS_MODEL = {
    "broken_elytra": "item/elytra_broken",
    "frosted_ice": "block/frosted_ice_0",
}
# Bedrock id -> a plain Java texture (GUI sprites etc.), rendered as a flat sprite
ALIAS_TEXTURE = {
    "empty_armor_slot_helmet": "gui/sprites/container/slot/helmet",
    "empty_armor_slot_chestplate": "gui/sprites/container/slot/chestplate",
    "empty_armor_slot_leggings": "gui/sprites/container/slot/leggings",
    "empty_armor_slot_boots": "gui/sprites/container/slot/boots",
    "empty_armor_slot_shield": "gui/sprites/container/slot/shield",
    "potion_overlay": "item/potion_overlay",
}
# Bedrock ids that do not exist in Java: build from a Java shape + another block's textures
SYNTH_STAIRS = {
    "cut_sandstone_stairs": "cut_sandstone_slab",
    "cut_red_sandstone_stairs": "cut_red_sandstone_slab",
}
# Structure-map texture keys
MAP_ALIAS = {
    "map_abandoned_campsite": "abandoned_camp_map", "map_ancient_city": "buried_ancient_city_map",
    "map_desert_pyramid": "desert_pyramid_map", "map_desert_village": "desert_village_map",
    "map_jungle_temple": "jungle_pyramid_map", "map_mansion": "woodland_mansion_map",
    "map_mineshaft": "buried_mineshaft_map", "map_monument": "ocean_monument_map",
    "map_plains_village": "plains_village_map", "map_savanna_village": "savanna_village_map",
    "map_snowy_village": "snowy_village_map", "map_swamp_hut": "swamp_hut_map",
    "map_taiga_village": "taiga_village_map", "map_trial_chambers": "buried_trial_chambers_map",
    "map_warm_ocean_ruins": "warm_ocean_ruins_map",
}
# Legacy `egg_<mob>` texture keys whose Java spawn-egg name is not just <mob>_spawn_egg
EGG_ALIAS = {
    "pigzombie": "zombified_piglin", "mushroomcow": "mooshroom", "lava_slime": "magma_cube",
    "polarbear": "polar_bear", "skeletonhorse": "skeleton_horse", "zombiehorse": "zombie_horse",
    "zombievillager": "zombie_villager", "wanderingtrader": "wandering_trader", "elderguardian": "elder_guardian",
    "glow_squid": "glow_squid", "cave_spider": "cave_spider", "clownfish": "tropical_fish",
    "tropicalfish": "tropical_fish", "pufferfish": "pufferfish",
}
OFFICIAL = set()   # official Bedrock item ids (when --ids is given)
LOW_CONFIDENCE = {
    "bed": "Bedrock `bed` is one base item with the colour in aux data; white_bed used as the stand-in (the site lists 16 colour variants).",
    "banner": "Bedrock `banner` is one base item with the colour in aux data; white_banner used as the stand-in.",
    "banner_pattern": "Bedrock has one generic banner_pattern item; Java has one per pattern. creeper_banner_pattern used as the stand-in.",
    "cave_vines": "Bedrock typeId is the block; the Java item is glow_berries.",
    "powder_snow": "Bedrock typeId is the block; the Java item is powder_snow_bucket.",
    "hoglin_meat_cooked": "Bedrock-only item name with no Java equivalent; cooked_porkchop used as a visual stand-in.",
    "hoglin_meat_raw": "Bedrock-only item name with no Java equivalent; porkchop used as a visual stand-in.",
    "lodestone_compass": "Java uses the same compass item with a lodestone component; the default compass model is shown.",
    "light_block_0": "Java `light` is one item with a level property; all 16 Bedrock ids share it.",
}

# Heuristic: ids that look like texture keys rather than real item typeIds.
TEXTURE_KEY_RE = re.compile(
    r"^(egg_.*|.*_atlas|bundle_.*_open(_front|_back)?|bundle_open(_front|_back)?|.*_pulling_\d|"
    r"crossbow_(arrow|firework)|map_.*|empty_armor_slot_.*|potion_overlay|fishing_rod_cast|"
    r"broken_elytra|boat_dark_oak|wolf_armor_dyed|dragon_fireball|chalkboard_.*|book_portfolio|ruby|quiver)$")
# map_locked / empty_map are real-ish; keep out of the texture-key bucket
NOT_TEXTURE_KEY = {"map_locked", "empty_map"}


# --------------------------------------------------------------------------
def norm(ref):
    if isinstance(ref, dict):  # newer texture format: {"sprite": "...", "force_translucent": true}
        ref = ref.get("sprite")
    return ref[len("minecraft:"):] if ref and ref.startswith("minecraft:") else ref


def argb_hex(v):
    return "#%06X" % (int(v) & 0xFFFFFF)


def load_bedrock_ids(html_path):
    s = open(html_path, encoding="utf-8").read()
    j = s.find("const DATA =") + len("const DATA =")
    data, _ = json.JSONDecoder().raw_decode(s[j:].lstrip())
    return [i for i, _ in data["items"]]


def load_icons(path):
    if not path or not os.path.exists(path):
        return {}
    a = open(path, encoding="utf-8").read()
    i = a.find("const ICONS = {")
    e = a.find("\n};", i)
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', a[i:e]))


class Java:
    def __init__(self, root):
        self.root = root
        self.items = {f[:-5] for f in os.listdir(f"{root}/items") if f.endswith(".json") and not f.startswith("_")}
        self._model_cache, self._flat_cache = {}, {}
        self.missing_textures, self.used_textures = set(), set()

    def model_exists(self, path):
        if path in self._model_cache:
            return True
        return os.path.exists(f"{self.root}/models/{path}.json")

    def raw_model(self, path):
        if path not in self._model_cache:
            self._model_cache[path] = json.load(open(f"{self.root}/models/{path}.json", encoding="utf-8"))
        return self._model_cache[path]

    def texture_file(self, path):
        return f"{self.root}/textures/{path}.png"

    def texture_info(self, path):
        f = self.texture_file(path)
        ok = os.path.exists(f)
        self.used_textures.add(path)
        if not ok:
            self.missing_textures.add(path)
        animated = False
        if os.path.exists(f + ".mcmeta"):
            try:
                animated = "animation" in json.load(open(f + ".mcmeta", encoding="utf-8"))
            except Exception:
                pass
        return ok, animated

    # ---- model flattening ------------------------------------------------
    def flatten(self, path, _stack=()):
        if path in self._flat_cache:
            return self._flat_cache[path]
        if path in _stack:
            raise RuntimeError("parent loop at " + path)
        d = self.raw_model(path)
        parent = norm(d.get("parent"))
        if parent is None:
            base = {"builtin": None, "textures": {}, "elements": None, "display": {}, "gui_light": None}
        elif parent.startswith("builtin/"):
            base = {"builtin": parent[8:], "textures": {}, "elements": None, "display": {}, "gui_light": None}
        else:
            b = self.flatten(parent, _stack + (path,))
            base = {"builtin": b["builtin"], "textures": dict(b["_vars"]), "elements": b["_elements"],
                    "display": {k: dict(v) for k, v in b["_display"].items()}, "gui_light": b["gui_light"]}
        base["textures"].update({k: norm(v) for k, v in d.get("textures", {}).items()})
        if "elements" in d:
            base["elements"] = d["elements"]
        for k, v in d.get("display", {}).items():
            base["display"].setdefault(k, {}).update(v)
        if d.get("gui_light"):
            base["gui_light"] = d["gui_light"]
        out = self._finish(path, base)
        self._flat_cache[path] = out
        return out

    @staticmethod
    def _resolve_var(vars_, val):
        seen = set()
        if isinstance(val, str) and not val.startswith("#") and "/" not in val and val in vars_:
            val = "#" + val  # vanilla quirk: face written as "all" instead of "#all"
        while isinstance(val, str) and val.startswith("#"):
            if val in seen or val[1:] not in vars_:
                return val  # unresolved
            seen.add(val)
            val = vars_[val[1:]]
        return val

    def _finish(self, path, base):
        vars_ = base["textures"]
        resolved = {k: self._resolve_var(vars_, v) for k, v in vars_.items()}
        out = {"builtin": base["builtin"], "gui_light": base["gui_light"] or "side",
               "_vars": vars_, "_elements": base["elements"], "_display": base["display"]}
        gui = base["display"].get("gui")
        if gui:
            out["gui"] = gui
        if base["elements"]:
            els, used = [], set()
            for e in base["elements"]:
                e = json.loads(json.dumps(e))
                for face in e.get("faces", {}).values():
                    t = self._resolve_var(vars_, face.get("texture"))
                    face["texture"] = t
                    used.add(t)
                els.append(e)
            out["elements"] = els
            out["shape"] = self._shape(els)
            out["textures_used"] = sorted(u for u in used if u)
        layers = sorted((k for k in resolved if re.fullmatch(r"layer\d+", k)), key=lambda k: int(k[5:]))
        if layers and not base["elements"]:
            out["layers"] = [resolved[k] for k in layers]
            out["textures_used"] = [resolved[k] for k in layers]
        out["textures"] = {k: v for k, v in resolved.items() if k != "particle"}
        return out

    @staticmethod
    def _shape(els):
        if len(els) == 1:
            e = els[0]
            if e.get("from") == [0, 0, 0] and e.get("to") == [16, 16, 16] and "rotation" not in e:
                return "cube"
        return "complex"

    # ---- item definitions --------------------------------------------------
    def item_def(self, jid):
        return json.load(open(f"{self.root}/items/{jid}.json", encoding="utf-8"))["model"]

    def walk(self, node, acc):
        """Pick the default branch of an item model definition; collect every other model as a variant."""
        t = norm(node.get("type", ""))
        if t == "model":
            tints = []
            for ti in node.get("tints", []):
                tt = norm(ti["type"])
                e = {"type": tt}
                if "default" in ti: e["default"] = argb_hex(ti["default"])
                if "value" in ti: e["value"] = argb_hex(ti["value"])
                tints.append(e)
            acc["models"].append({"model": norm(node["model"]), "tints": tints})
            return {"model": norm(node["model"]), "tints": tints}
        if t == "select":
            cases = [c["model"] for c in node.get("cases", [])]
            fb = node.get("fallback")
            if fb:
                primary = self.walk(fb, acc)
                for c in cases: self.walk(c, acc)
            else:
                primary = self.walk(cases[0], acc)
                for c in cases[1:]: self.walk(c, acc)
            return primary
        if t == "condition":
            primary = self.walk(node["on_false"], acc)
            if node.get("on_true"): self.walk(node["on_true"], acc)
            return primary
        if t == "range_dispatch":
            entries = node.get("entries", [])
            fb = node.get("fallback")
            if fb:
                primary = self.walk(fb, acc)
                for en in entries: self.walk(en["model"], acc)
            else:
                primary = self.walk(entries[0]["model"], acc)
                for en in entries[1:]: self.walk(en["model"], acc)
            return primary
        if t == "composite":
            parts = [self.walk(m, acc) for m in node.get("models", [])]
            return {"parts": parts}
        if t == "special":
            sp = node.get("model", {})
            res = {"special": {k: norm(v) if isinstance(v, str) else v for k, v in sp.items()}, "base": norm(node.get("base"))}
            acc["special"] = True
            return res
        if t == "empty":
            return {"empty": True}
        if t == "bundle/selected_item":
            return {}
        return {"unhandled": t}


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    here = "/tmp/kwb"
    ap.add_argument("--java", default=here + "/Java Assets Folder - VISUAL ONLY/Java Assets Folder - VISUAL ONLY/assets/minecraft")
    ap.add_argument("--html", default=here + "/KitX Web Builder/KitX Web Builder/index.html")
    ap.add_argument("--icons", default=here + "/addon/KitX_BP/scripts/item_icons.js")
    ap.add_argument("--out", default="out")
    ap.add_argument("--ids", help="mojang-items.json (official Bedrock item ids); the old --html ids are kept as extras")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    J = Java(a.java)
    if a.ids:
        official = [x["name"].replace("minecraft:", "") for x in json.load(open(a.ids, encoding="utf-8"))["data_items"]]
        old = load_bedrock_ids(a.html) if a.html and os.path.exists(a.html) else []
        ids = official + [i for i in old if i not in set(official)]
        OFFICIAL.update(official)
    else:
        ids = load_bedrock_ids(a.html)
    icons = load_icons(a.icons)

    models_out, mapping = {}, {}
    used_java = set()

    def need_model(mid):
        if mid not in models_out:
            if not J.model_exists(mid):
                models_out[mid] = {"missing": True}
            else:
                m = J.flatten(mid)
                models_out[mid] = {k: v for k, v in m.items() if not k.startswith("_")}
                for t in m.get("textures_used", []):
                    J.texture_info(t)
        return models_out[mid]

    def classify_model(mid):
        m = need_model(mid)
        if m.get("missing"): return "missing"
        if m["builtin"] == "generated" and m.get("layers"): return "sprite"
        if m["builtin"] == "entity": return "entity"
        if m.get("elements"): return "cube" if m.get("shape") == "cube" else "model3d"
        return "unknown"

    for bid in ids:
        e = {}
        via = jid = jmodel = None
        conf = "high"
        # 1. explicit override / exact / alias
        if bid in OVERRIDE_ITEM and OVERRIDE_ITEM[bid] in J.items:
            jid, via = OVERRIDE_ITEM[bid], "override"
        elif bid in J.items:
            jid, via = bid, "exact"
        elif bid in ALIAS_ITEM and ALIAS_ITEM[bid] in J.items:
            jid, via = ALIAS_ITEM[bid], "alias"
        elif bid.startswith("waxed_") and bid[6:] in J.items:
            jid, via = bid[6:], "alias"          # waxed copper uses the same model as the unwaxed one
        elif bid in MAP_ALIAS and MAP_ALIAS[bid] in J.items:
            jid, via = MAP_ALIAS[bid], "alias"
        elif bid.startswith("egg_"):
            mob = bid[4:]
            cand = EGG_ALIAS.get(mob, mob) + "_spawn_egg"
            if cand in J.items:
                jid, via = cand, "rule"
        elif re.fullmatch(r"light_block_\d+", bid):
            jid, via = "light", "alias"
            jmodel = "item/light_%02d" % int(bid.split("_")[-1])
        # 1b. bundle open-state texture keys: bundle_<color>_open[_back|_front]
        bundle_parts = None
        mb = re.fullmatch(r"bundle_(?:(.+?)_)?open(_back|_front)?", bid)
        if not jid and mb:
            color, half = mb.group(1), mb.group(2)
            pre = (color + "_") if color else ""
            jid, via = pre + "bundle", "rule"
            if jid not in J.items:
                jid = None
            elif half:
                jmodel = f"item/{pre}bundle_open{half}"
            else:
                bundle_parts = [f"item/{pre}bundle_open_back", f"item/{pre}bundle_open_front"]
        # 2. direct model fallback
        if not jid:
            if bid in ALIAS_MODEL and J.model_exists(ALIAS_MODEL[bid]):
                jmodel, via = ALIAS_MODEL[bid], "model"
            elif J.model_exists("item/" + bid):
                jmodel, via = "item/" + bid, "model"
            elif J.model_exists("block/" + bid):
                jmodel, via = "block/" + bid, "model"

        tex_alias = ALIAS_TEXTURE.get(bid)
        synth = SYNTH_STAIRS.get(bid)
        mcw = re.fullmatch(r"(.+)_(concrete|wool)_(slab|stairs)", bid)
        if mcw and not jid and not jmodel:
            mat = mcw.group(1) + "_" + mcw.group(2)
            tx = "block/" + mat
            J._model_cache["synth/" + bid] = {"parent": "minecraft:block/" + mcw.group(3),
                                              "textures": {"bottom": tx, "top": tx, "side": tx}}
            jmodel, via = "synth/" + bid, "synth"
            LOW_CONFIDENCE[bid] = "Does not exist in Java: " + mcw.group(3) + " shape built with the " + mat + " texture."
        if tex_alias and not jid and not jmodel:
            via = "texture"
        if synth and not jid and not jmodel and J.model_exists("block/" + synth):
            slab = J.raw_model("block/" + synth)
            J._model_cache["synth/" + bid] = {"parent": "minecraft:block/stairs", "textures": slab["textures"]}
            jmodel, via = "synth/" + bid, "synth"
            LOW_CONFIDENCE[bid] = "Does not exist in Java: stairs shape built with the textures of " + synth + "."
        if via in ("alias", "rule", "override"):
            conf = "medium"
        if bid in LOW_CONFIDENCE:
            conf = "low"

        e["via"] = via or "none"
        e["confidence"] = conf if via else None
        if bid in NOT_TEXTURE_KEY or not TEXTURE_KEY_RE.match(bid):
            e["class"] = "item" if via else "bedrock_only"
        else:
            e["class"] = "texture_key" if via else "texture_key"
        if bid in LOW_CONFIDENCE:
            e["note"] = LOW_CONFIDENCE[bid]
        if bid in icons:
            e["bedrock_icon"] = icons[bid]

        if jid:
            used_java.add(jid)
            e["java_item"] = jid
            acc = {"models": [], "special": False}
            res = J.walk(J.item_def(jid), acc)
            variants = []
            if bundle_parts:
                res = {"parts": [{"model": m, "tints": []} for m in bundle_parts]}
            elif jmodel:  # forced variant (e.g. light level, bundle open half)
                res = {"model": jmodel, "tints": []}
            if "model" in res:
                e["model"] = res["model"]
                if res["tints"]: e["tints"] = res["tints"]
                e["render"] = classify_model(res["model"])
            elif "parts" in res:
                e["render"] = "composite"
                e["parts"] = []
                for p in res["parts"]:
                    if "model" in p:
                        classify_model(p["model"])
                        e["parts"].append({"model": p["model"], **({"tints": p["tints"]} if p.get("tints") else {})})
                    else:
                        e["parts"].append(p)
            elif "special" in res:
                e["render"] = "special"
                e["special"] = res["special"]
                if res.get("base"):
                    e["model"] = res["base"]
                    classify_model(res["base"])
            else:
                e["render"] = "none"
                e["note"] = (e.get("note", "") + " unhandled item definition " + json.dumps(res)).strip()
            main_models = {e.get("model")} | {p.get("model") for p in e.get("parts", [])}
            variants = sorted({m["model"] for m in acc["models"]} - main_models - {None})
            variants = [v for v in variants if "_trim" not in v]  # trim textures are generated at runtime in Java
            if variants:
                e["variants"] = variants
                for v in variants: need_model(v)
        elif via == "texture":
            ok, _ = J.texture_info(tex_alias)
            e["java_item"] = None
            e["render"] = "sprite"
            e["textures"] = [tex_alias]
            e["confidence"] = "medium"
        elif jmodel:
            e["java_item"] = None
            e["model"] = jmodel
            e["render"] = classify_model(jmodel)
        else:
            e["java_item"] = None
            e["render"] = "none"
        mapping[bid] = e

    # texture existence for everything referenced by sprite/model entries is collected in need_model
    animated = sorted(t for t in J.used_textures if J.texture_info(t)[1])

    out_map = {
        "meta": {
            "bedrock_ids": len(ids), "java_items": len(J.items), "java_items_used": len(used_java),
            "models_resolved": len(models_out), "animated_textures": animated,
            "missing_textures": sorted(J.missing_textures),
            "note": "Texture paths are relative to assets/minecraft/textures/ and have no extension (.png). "
                    "Animated textures (see animated_textures) are vertical strips: use the first square frame.",
        },
        "items": mapping,
    }
    json.dump(out_map, open(f"{a.out}/bedrock_to_java_map.json", "w"), indent=1)
    json.dump(models_out, open(f"{a.out}/java_models_resolved.json", "w"), separators=(",", ":"))

    # ---------------- report ----------------
    by_via = collections.Counter(v["via"] for v in mapping.values())
    by_render = collections.Counter(v["render"] for v in mapping.values())
    by_class = collections.Counter(v["class"] for v in mapping.values())
    L = []
    L.append("# Bedrock -> Java mapping report\n")
    L.append(f"Bedrock ids: **{len(ids)}**, Java item definitions: **{len(J.items)}**, Java items used: **{len(used_java)}**, models resolved: **{len(models_out)}**\n")
    L.append("## Match method\n" + "\n".join(f"- {k}: {v}" for k, v in by_via.most_common()))
    L.append("\n## Render type\n" + "\n".join(f"- {k}: {v}" for k, v in by_render.most_common()))
    L.append("\n## Id class (heuristic)\n" + "\n".join(f"- {k}: {v}" for k, v in by_class.most_common()))
    none_ids = [b for b, v in mapping.items() if v["via"] == "none"]
    L.append(f"\n## No Java equivalent found ({len(none_ids)})\n" + ", ".join(f"`{b}`" for b in none_ids))
    low = [(b, v["note"]) for b, v in mapping.items() if v.get("confidence") == "low"]
    L.append(f"\n## Low confidence ({len(low)})\n" + "\n".join(f"- `{b}`: {n}" for b, n in low))
    spec = [(b, v["special"].get("type", "?")) for b, v in mapping.items() if v["render"] == "special"]
    L.append(f"\n## Special (entity-rendered) items ({len(spec)})\n" + ", ".join(f"`{b}` ({t})" for b, t in spec))
    comp = [b for b, v in mapping.items() if v["render"] == "composite"]
    L.append(f"\n## Composite items ({len(comp)})\n" + ", ".join(f"`{b}`" for b in comp))
    unk = [b for b, v in mapping.items() if v["render"] in ("unknown", "missing", "entity")]
    L.append(f"\n## Render unknown / entity / missing model ({len(unk)})\n" + ", ".join(f"`{b}`" for b in unk))
    L.append(f"\n## Missing texture files ({len(J.missing_textures)})\n" + ", ".join(f"`{t}`" for t in sorted(J.missing_textures)))
    jo = sorted(J.items - used_java)
    L.append(f"\n## Java items with no Bedrock id in the list ({len(jo)})\n" + ", ".join(f"`{j}`" for j in jo))
    open(f"{a.out}/mapping_report.md", "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
