"""Bedrock-style creative inventory layout.
Each tab is an ordered list of entries:  'G:<Group title>'  -> a collapsible group (members from groups.py rules/sets)
                                         '<item id>'          -> a single item
Order follows the screenshots of the real creative inventory where they were readable; items marked (?) were
identified by eye and may need correcting. Anything listed in no tab is appended to the best-guess tab by the build."""
EXTRA_GROUPS = {   # groups defined by explicit id lists (title -> ids, in display order)
 'Decorative Stone': ['stone_bricks','mossy_stone_bricks','cracked_stone_bricks','chiseled_stone_bricks','smooth_stone','deepslate_bricks','cracked_deepslate_bricks','deepslate_tiles','cracked_deepslate_tiles','chiseled_deepslate','polished_deepslate','polished_blackstone','polished_blackstone_bricks','cracked_polished_blackstone_bricks','chiseled_polished_blackstone','gilded_blackstone','polished_tuff','tuff_bricks','chiseled_tuff','chiseled_tuff_bricks','polished_cinnabar','cinnabar_bricks','chiseled_cinnabar','polished_sulfur','sulfur_bricks','chiseled_sulfur'],
 'Sandstone': ['sandstone','chiseled_sandstone','cut_sandstone','smooth_sandstone','red_sandstone','chiseled_red_sandstone','cut_red_sandstone','smooth_red_sandstone'],
 'Stone': ['stone','granite','polished_granite','diorite','polished_diorite','andesite','polished_andesite','deepslate','tuff','calcite','blackstone','basalt','smooth_basalt','polished_basalt'],
 'Infested Stone': ['infested_stone','infested_cobblestone','infested_stone_bricks','infested_mossy_stone_bricks','infested_cracked_stone_bricks','infested_chiseled_stone_bricks','infested_deepslate'],
 'Nether Warts': ['nether_wart_block','warped_wart_block'],
 'Sculk': ['sculk','sculk_vein','sculk_catalyst','sculk_sensor','calibrated_sculk_sensor','sculk_shrieker'],
 'Coral Blocks': ['tube_coral_block','brain_coral_block','bubble_coral_block','fire_coral_block','horn_coral_block','dead_tube_coral_block','dead_brain_coral_block','dead_bubble_coral_block','dead_fire_coral_block','dead_horn_coral_block'],
 'Coral Decorations': ['tube_coral','brain_coral','bubble_coral','fire_coral','horn_coral','tube_coral_fan','brain_coral_fan','bubble_coral_fan','fire_coral_fan','horn_coral_fan','dead_tube_coral','dead_brain_coral','dead_bubble_coral','dead_fire_coral','dead_horn_coral','dead_tube_coral_fan','dead_brain_coral_fan','dead_bubble_coral_fan','dead_fire_coral_fan','dead_horn_coral_fan'],
 'Seeds': ['wheat_seeds','melon_seeds','pumpkin_seeds','beetroot_seeds','torchflower_seeds','pitcher_pod'],
 'Crops': ['wheat','carrot','potato','beetroot','sweet_berries','glow_berries','cocoa_beans','sugar_cane','melon_slice','nether_wart'],
 'Flowers': ['dandelion','golden_dandelion','poppy','blue_orchid','allium','azure_bluet','red_tulip','orange_tulip','white_tulip','pink_tulip','oxeye_daisy','cornflower','lily_of_the_valley','wither_rose','torchflower','closed_eyeblossom','open_eyeblossom','sunflower','lilac','rose_bush','peony','pink_petals','wildflowers'],
 'Mushrooms': ['red_mushroom','brown_mushroom','crimson_fungus','warped_fungus','shelf_mushroom','shroomlight','red_mushroom_block','brown_mushroom_block','mushroom_stem'],
 'Ground Cover': ['short_grass','tall_grass','fern','large_fern','short_dry_grass','tall_dry_grass','bush','deadbush','leaf_litter','vine','glow_lichen','hanging_roots','pale_hanging_moss','seagrass','kelp','sea_pickle','waterlily','web','moss_block','pale_moss_block','azalea','flowering_azalea','big_dripleaf','small_dripleaf_block','spore_blossom','twisting_vines','weeping_vines','crimson_roots','warped_roots','nether_sprouts','chorus_plant','chorus_flower','firefly_bush','red_shrub'],
 'Raw Food': ['apple','beef','porkchop','chicken','mutton','rabbit','cod','salmon','tropical_fish','pufferfish','potato','poisonous_potato','carrot','beetroot','rotten_flesh','spider_eye','chorus_fruit','sweet_berries','glow_berries','dried_kelp','melon_slice','golden_apple','enchanted_golden_apple','golden_carrot','glistering_melon_slice'],
 'Cooked Food': ['cooked_beef','cooked_porkchop','cooked_chicken','cooked_mutton','cooked_rabbit','cooked_cod','cooked_salmon','baked_potato','dried_kelp'],
 'Miscellaneous Foods': ['bread','cookie','cake','pumpkin_pie','mushroom_stew','rabbit_stew','beetroot_soup','suspicious_stew','honey_bottle','milk_bucket','golden_apple','enchanted_golden_apple','golden_carrot','glistering_melon_slice','apple'],
 'Dyes': [],   # filled from rule *_dye
 'Copper': [],  # filled from rule (copper blocks), see build
}
CONSTRUCTION = ['G:Planks','G:Walls','G:Fences','G:Fence Gates','G:Stairs','G:Doors','G:Trapdoors',
 'G:Bars','G:Glass','G:Glass Panes','ladder','scaffolding','brick_block','G:Slabs',
 'G:Decorative Stone','cobblestone','mossy_cobblestone','cobbled_deepslate','G:Sandstone','obsidian','crying_obsidian','dried_kelp_block',
 'G:Copper','iron_block','gold_block','emerald_block','diamond_block','lapis_block','coal_block','netherite_block','raw_copper_block','raw_iron_block','raw_gold_block',
 'quartz_block','chiseled_quartz_block','quartz_pillar','quartz_bricks','smooth_quartz',
 'prismarine','prismarine_bricks','dark_prismarine','slime','honey_block','honeycomb_block','magma',
 'hay_block','bone_block','resin_block','resin_bricks','chiseled_resin_bricks','nether_brick','red_nether_brick','chiseled_nether_bricks','cracked_nether_bricks','end_bricks','reinforced_deepslate',
 'G:Wool','G:Wool Carpet','G:Concrete Powder','G:Concrete','G:Terracotta','G:Glazed Terracottas','purpur_block','purpur_pillar','packed_mud','mud_bricks']
EQUIPMENT = ['G:Helmets','G:Chestplates','G:Leggings','G:Boots','G:Swords','G:Spears','G:Axes',
 'G:Pickaxes','G:Shovels','G:Hoes','bow','crossbow','mace','trident',
 'G:Arrows','shield','G:Cooked Food','G:Miscellaneous Foods','fishing_rod','carrot_on_a_stick','warped_fungus_on_a_stick',
 'snowball','wind_charge','shears','flint_and_steel','lead','clock','compass',
 'recovery_compass','lodestone_compass','G:Goat Horns','empty_map','filled_map','saddle','G:Harnesses','G:Bundles',
 'G:Horse Armor','wolf_armor','G:Nautilus Armor','turtle_scute','elytra','totem_of_undying','glass_bottle',
 'experience_bottle','G:Potions','G:Splash Potions','G:Lingering Potions','G:Ominous Bottles','spyglass','brush']
ITEMS = ['stick','G:Beds','straw_bed','G:Cushions','torch','soul_torch','copper_torch','redstone_torch','G:Lanterns','G:Candles',
 'crafting_table','cartography_table','fletching_table','smithing_table','loom','stonecutter_block','grindstone',
 'campfire','soul_campfire','furnace','blast_furnace','smoker','respawn_anchor','lodestone','end_rod','G:Anvils',
 'enchanting_table','bookshelf','chiseled_bookshelf','G:Shelves','lectern','cauldron','brewing_stand','composter','barrel','G:Chests','G:Shulker Boxes',
 'armor_stand','noteblock','jukebox','G:Records','glowstone','redstone_lamp','sea_lantern','G:Signs','G:Hanging Signs',
 'frame','glow_frame','painting','flower_pot','bowl','bucket','water_bucket','lava_bucket','powder_snow_bucket','cod_bucket','salmon_bucket','tropical_fish_bucket','pufferfish_bucket','tadpole_bucket','axolotl_bucket','sulfur_cube_bucket',
 'G:Mob Skulls','G:Lightning Rods','conduit','beacon','bell','heavy_core',
 'coal','charcoal','diamond','emerald','quartz','amethyst_shard','echo_shard','prismarine_shard','prismarine_crystals','nautilus_shell','heart_of_the_sea','armadillo_scute','resin_clump','resin_brick','brick','netherbrick','clay_ball','flint',
 'iron_ingot','iron_nugget','raw_iron','gold_ingot','gold_nugget','raw_gold','copper_ingot','copper_nugget','raw_copper','netherite_ingot','netherite_scrap','lapis_lazuli','redstone',
 'feather','leather','rabbit_hide','rabbit_foot','string','slime_ball','ink_sac','glow_ink_sac','bone','bone_meal','gunpowder','glowstone_dust','blaze_powder','blaze_rod','breeze_rod','ghast_tear','magma_cream','fermented_spider_eye','phantom_membrane','shulker_shell','dragon_breath','ender_pearl','ender_eye','popped_chorus_fruit','nether_star','sugar','paper','book','writable_book','name_tag','fire_charge','end_crystal','G:Dyes',
 'G:Enchanted Books','G:Boats','G:Boats with Chest','G:Rails','G:Minecarts','redstone_block','lever','tripwire_hook','G:Buttons','G:Pressure Plates','repeater','comparator','hopper','dropper','dispenser','observer','piston','sticky_piston','daylight_detector','tnt','target','crafter','command_block','chain_command_block','repeating_command_block','structure_block','jigsaw',
 'G:Banners','G:Banner Patterns','G:Pottery Sherds','G:Smithing Templates','G:Fireworks','G:Firework Charges','G:Chains','decorated_pot','trial_key','ominous_trial_key','trial_spawner','vault','G:Light Blocks','barrier','structure_void','mob_spawner']
NATURE = ['netherrack','crimson_nylium','warped_nylium','G:Nether Warts','shroomlight','soul_sand','soul_soil','basalt',
 'grass_block','podzol','mycelium','farmland','grass_path','dirt','coarse_dirt','dirt_with_roots','mud','muddy_mangrove_roots','mangrove_roots','clay','gravel','sand','red_sand','suspicious_sand','suspicious_gravel',
 'G:Ores','ancient_debris','G:Stone','G:Infested Stone','end_stone','bedrock','cactus','G:Logs','G:Woods','G:Leaves','G:Saplings','bee_nest','beehive',
 'G:Seeds','G:Crops','pumpkin','carved_pumpkin','lit_pumpkin','melon_block','honeycomb','G:Coral Blocks','G:Coral Decorations','G:Flowers','G:Mushrooms','G:Ground Cover',
 'sponge','wet_sponge','snow','snow_layer','ice','packed_ice','blue_ice','dripstone_block','pointed_dripstone','amethyst_block','budding_amethyst','small_amethyst_bud','medium_amethyst_bud','large_amethyst_bud','amethyst_cluster',
 'cactus_flower','bamboo','bamboo_block','pitcher_plant','sniffer_egg','turtle_egg','frog_spawn','egg','blue_egg','brown_egg','dragon_egg','creaking_heart','dried_ghast','ochre_froglight','verdant_froglight','pearlescent_froglight',
 'cinnabar','sulfur','potent_sulfur','sulfur_spike','end_portal_frame','G:Raw Food','G:Sculk','G:Mob Eggs']
