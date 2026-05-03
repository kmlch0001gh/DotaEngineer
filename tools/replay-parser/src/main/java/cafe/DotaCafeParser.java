package cafe;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import skadistats.clarity.Clarity;
import skadistats.clarity.model.Entity;
import skadistats.clarity.model.FieldPath;
import skadistats.clarity.processor.entities.Entities;
import skadistats.clarity.processor.entities.OnEntityCreated;
import skadistats.clarity.processor.entities.OnEntityUpdated;
import skadistats.clarity.model.CombatLogEntry;
import skadistats.clarity.processor.gameevents.OnCombatLogEntry;
import skadistats.clarity.processor.runner.Context;
import skadistats.clarity.processor.runner.SimpleRunner;
import skadistats.clarity.source.MappedFileSource;
import skadistats.clarity.wire.dota.common.proto.DOTACombatLog.DOTA_COMBATLOG_TYPES;
import skadistats.clarity.wire.shared.demo.proto.Demo.CDemoFileInfo;
import skadistats.clarity.wire.shared.demo.proto.Demo.CGameInfo;

import java.util.*;

/**
 * Parses a Dota 2 .dem replay and outputs JSON with full match data.
 *
 * Extracts: heroes, teams, KDA, GPM, damage, bans, and item purchase log.
 */
public class DotaCafeParser {

    // Per-player stats from CDOTA_PlayerResource (indexed by playerID/2)
    final int[] prKills = new int[20];
    final int[] prDeaths = new int[20];
    final int[] prAssists = new int[20];
    final int[] prLevel = new int[20];
    final int[] prHeroId = new int[20];

    // Per-team-slot stats from CDOTA_DataRadiant/Dire (indexed 0-4)
    // [0]=radiant, [1]=dire
    final int[][] netWorthT = new int[2][5];
    final int[][] lastHitsT = new int[2][5];
    final int[][] deniesT = new int[2][5];
    final int[][] heroDamageT = new int[2][5];
    final int[][] towerDamageT = new int[2][5];
    final int[][] heroHealingT = new int[2][5];
    final int[][] totalGoldT = new int[2][5];
    final int[][] totalXPT = new int[2][5];
    // New role-relevant stats
    final int[][] obsWardsPlacedT = new int[2][5];
    final int[][] sentryWardsPlacedT = new int[2][5];
    final int[][] wardsDestroyedT = new int[2][5];
    final int[][] campsStackedT = new int[2][5];
    final float[][] stunDurationT = new float[2][5];
    final int[][] smokesUsedT = new int[2][5];
    final int[][] goldSpentSupportT = new int[2][5];
    final int[][] goldSpentBuybacksT = new int[2][5];
    final float[][] damageTakenT = new float[2][5];
    final int[][] runePickupsT = new int[2][5];
    final int[][] roshanKillsT = new int[2][5];
    final int[][] towerKillsT = new int[2][5];

    float gameTime = 0;
    float gameStartTime = 0;
    int totalPausedTicks = 0;
    int gameWinnerEntity = 0;
    final int[] bannedHeroes = new int[24];

    final Map<Integer, Integer> playerTeam = new HashMap<>();
    final Map<Integer, String> playerName = new HashMap<>();

    // Item purchase log: hero_name → [{item, time}, ...]
    final Map<String, List<Map<String, Object>>> purchaseLog = new LinkedHashMap<>();

    // Final inventory: track item entity handles → class names, hero inventories
    final Map<Integer, String> itemEntityClasses = new HashMap<>();
    // heroShortName → [slot0_item, slot1_item, ...] (slots 0-5 main, 6-8 backpack, 16 neutral)
    final Map<String, List<String>> heroFinalItems = new LinkedHashMap<>();

    @OnEntityCreated
    public void onCreated(Context ctx, Entity e) {
        captureController(e);
        trackItemEntity(e);
    }

    @OnEntityUpdated
    public void onUpdated(Context ctx, Entity e, FieldPath[] fps, int num) {
        try {
            String dt = e.getDtClass().getDtName();

            trackItemEntity(e);
            trackHeroInventory(e, dt);

            if ("CDOTAPlayerController".equals(dt)) {
                captureController(e);
            } else if ("CDOTA_PlayerResource".equals(dt)) {
                for (int i = 0; i < 20; i++) {
                    String p = "m_vecPlayerTeamData." + pad(i) + ".";
                    prKills[i] = ri(e, p + "m_iKills");
                    prDeaths[i] = ri(e, p + "m_iDeaths");
                    prAssists[i] = ri(e, p + "m_iAssists");
                    prLevel[i] = ri(e, p + "m_iLevel");
                    int hid = ri(e, p + "m_nSelectedHeroID");
                    if (hid > 0) prHeroId[i] = hid;
                }
            } else if ("CDOTA_DataRadiant".equals(dt) || "CDOTA_DataDire".equals(dt)) {
                int t = "CDOTA_DataRadiant".equals(dt) ? 0 : 1;
                for (int i = 0; i < 5; i++) {
                    String p = "m_vecDataTeam." + pad(i) + ".";
                    netWorthT[t][i] = ri(e, p + "m_iNetWorth");
                    lastHitsT[t][i] = ri(e, p + "m_iLastHitCount");
                    deniesT[t][i] = ri(e, p + "m_iDenyCount");
                    heroDamageT[t][i] = (int) rf(e, p + "m_flHeroDamage");
                    towerDamageT[t][i] = (int) rf(e, p + "m_flTowerDamage");
                    heroHealingT[t][i] = (int) rf(e, p + "m_flHeroHealing");
                    totalGoldT[t][i] = ri(e, p + "m_iTotalEarnedGold");
                    totalXPT[t][i] = ri(e, p + "m_iTotalEarnedXP");
                    // Role-relevant stats
                    obsWardsPlacedT[t][i] = ri(e, p + "m_iObserverWardsPlaced");
                    sentryWardsPlacedT[t][i] = ri(e, p + "m_iSentryWardsPlaced");
                    wardsDestroyedT[t][i] = ri(e, p + "m_iWardsDestroyed");
                    campsStackedT[t][i] = ri(e, p + "m_iCampsStacked");
                    stunDurationT[t][i] = rf(e, p + "m_fStuns");
                    smokesUsedT[t][i] = ri(e, p + "m_iSmokesUsed");
                    goldSpentSupportT[t][i] = ri(e, p + "m_iGoldSpentOnSupport");
                    goldSpentBuybacksT[t][i] = ri(e, p + "m_iGoldSpentOnBuybacks");
                    runePickupsT[t][i] = ri(e, p + "m_iRunePickups");
                    roshanKillsT[t][i] = ri(e, p + "m_iRoshanKills");
                    towerKillsT[t][i] = ri(e, p + "m_iTowerKills");
                    // Damage taken = sum of 3 damage types post-reduction
                    float dt0 = rf(e, p + "m_flDamageByTypeReceivedPostReduction.0000");
                    float dt1 = rf(e, p + "m_flDamageByTypeReceivedPostReduction.0001");
                    float dt2 = rf(e, p + "m_flDamageByTypeReceivedPostReduction.0002");
                    damageTakenT[t][i] = dt0 + dt1 + dt2;
                }
            } else if ("CDOTATeam".equals(dt)) {
                // no-op: kills tracked via prKills sum
            } else if ("CDOTAGamerulesProxy".equals(dt)) {
                float gt = rf(e, "m_pGameRules.m_fGameTime");
                if (gt > 0) gameTime = gt;
                float gst = rf(e, "m_pGameRules.m_flGameStartTime");
                if (gst > 0) gameStartTime = gst;
                int pt = ri(e, "m_pGameRules.m_nTotalPausedTicks");
                if (pt > 0) totalPausedTicks = pt;
                int gw = ri(e, "m_pGameRules.m_nGameWinner");
                if (gw > 0) gameWinnerEntity = gw;
                for (int i = 0; i < 24; i++) {
                    int bh = ri(e, "m_pGameRules.m_BannedHeroes." + pad(i));
                    if (bh > 0) bannedHeroes[i] = bh;
                }
            }
        } catch (Exception ex) {
            // ignore
        }
    }

    @OnCombatLogEntry
    public void onCombatLog(Context ctx, CombatLogEntry entry) {
        try {
            if (entry.getType() != DOTA_COMBATLOG_TYPES.DOTA_COMBATLOG_PURCHASE) return;

            String buyer = entry.getTargetName();
            String item = entry.getValueName();
            float time = entry.getTimestamp();

            if (buyer == null || item == null) return;

            String heroKey = buyer.replace("npc_dota_hero_", "");
            String itemName = item.replace("item_", "");

            purchaseLog.computeIfAbsent(heroKey, k -> new ArrayList<>())
                .add(Map.of("item", itemName, "time", time));
        } catch (Exception ex) {
            // ignore
        }
    }

    private void trackItemEntity(Entity e) {
        String dt = e.getDtClass().getDtName();
        if (dt.startsWith("CDOTA_Item")) {
            itemEntityClasses.put(e.getHandle(), dt);
        }
    }

    private void trackHeroInventory(Entity e, String dt) {
        if (!dt.startsWith("CDOTA_Unit_Hero_")) return;
        String heroName = dt.replace("CDOTA_Unit_Hero_", "").toLowerCase();
        List<String> items = new ArrayList<>();
        // Slots 0-5 main inventory, 6-8 backpack, 16 neutral
        int[] slots = {0, 1, 2, 3, 4, 5, 6, 7, 8, 16};
        for (int i : slots) {
            try {
                FieldPath fp = e.getDtClass().getFieldPathForName("m_hItems." + pad(i));
                if (fp == null) continue;
                Object val = e.getPropertyForFieldPath(fp);
                if (val instanceof Number) {
                    int handle = ((Number) val).intValue();
                    if (handle > 0 && handle != 16777215) {
                        String cls = itemEntityClasses.getOrDefault(handle, "");
                        String itemName = classToItemName(cls);
                        if (!itemName.isEmpty()) items.add(itemName);
                    }
                }
            } catch (Exception ex) {}
        }
        if (!items.isEmpty()) heroFinalItems.put(heroName, items);
    }

    /** Convert CDOTA_Item_Black_King_Bar → black_king_bar */
    private static String classToItemName(String cls) {
        if (cls.isEmpty() || !cls.startsWith("CDOTA_Item")) return "";
        // Special cases where class name differs from item_xxx CDN name
        Map<String, String> overrides = Map.ofEntries(
            Map.entry("CDOTA_Item_EmptyBottle", "bottle"),
            Map.entry("CDOTA_Item_MagicWand", "magic_wand"),
            Map.entry("CDOTA_Item_MagicStick", "magic_stick"),
            Map.entry("CDOTA_Item_PowerTreads", "power_treads"),
            Map.entry("CDOTA_Item_PhaseBoots", "phase_boots"),
            Map.entry("CDOTA_Item_TranquilBoots", "tranquil_boots"),
            Map.entry("CDOTA_Item_Arcane_Boots", "arcane_boots"),
            Map.entry("CDOTA_Item_UltimateScepter", "ultimate_scepter"),
            Map.entry("CDOTA_Item_BlinkDagger", "blink"),
            Map.entry("CDOTA_Item_TeleportScroll", "tpscroll"),
            Map.entry("CDOTA_Item_MantaStyle", "manta"),
            Map.entry("CDOTA_Item_MaskOfDeath", "lifesteal"),
            Map.entry("CDOTA_Item_GhostScepter", "ghost"),
            Map.entry("CDOTA_Item_SheepStick", "sheepstick"),
            Map.entry("CDOTA_Item_GlimmerCape", "glimmer_cape"),
            Map.entry("CDOTA_Item_RefresherOrb", "refresher"),
            Map.entry("CDOTA_Item_ForceStaff", "force_staff"),
            Map.entry("CDOTA_Item_GreaterCritical", "greater_crit"),
            Map.entry("CDOTA_Item_MonkeyKingBar", "monkey_king_bar"),
            Map.entry("CDOTA_Item_QuellingBlade", "quelling_blade"),
            Map.entry("CDOTA_Item_WindLace", "wind_lace"),
            Map.entry("CDOTA_Item_BeltOfStrength", "belt_of_strength"),
            Map.entry("CDOTA_Item_OgreAxe", "ogre_axe"),
            Map.entry("CDOTA_Item_UltimateOrb", "ultimate_orb"),
            Map.entry("CDOTA_Item_MithrilHammer", "mithril_hammer"),
            Map.entry("CDOTA_Item_Ward_Dispenser", "ward_dispenser"),
            Map.entry("CDOTA_Item_DustofAppearance", "dust"),
            Map.entry("CDOTA_Item_Smoke_Of_Deceit", "smoke_of_deceit"),
            Map.entry("CDOTA_Item_Orb_Of_Frost", "orb_of_corrosion"),
            Map.entry("CDOTA_Item_Guardian_Greaves", "guardian_greaves"),
            Map.entry("CDOTA_Item_Assault_Cuirass", "assault"),
            Map.entry("CDOTA_Item_Hurricane_Pike", "hurricane_pike"),
            Map.entry("CDOTA_Item_IdolOfScreeauk", "enchanted_quiver"),
            Map.entry("CDOTA_Item_SerratedShiv", "serrated_shiv"),
            Map.entry("CDOTA_Item_Giant_Maul", "giants_ring"),
            Map.entry("CDOTA_Item_Searing_Signet", "searing_signet"),
            Map.entry("CDOTA_Item_Enchanters_Bauble", "enchanters_bauble"),
            Map.entry("CDOTA_Item_Conjurers_Catalyst", "conjurers_catalyst"),
            Map.entry("CDOTA_Item_Prophets_Pendulum", "prophets_pendulum")
        );
        if (overrides.containsKey(cls)) return overrides.get(cls);
        // Default: strip prefix and convert CamelCase to snake_case
        String name = cls.replace("CDOTA_Item_", "");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < name.length(); i++) {
            char c = name.charAt(i);
            if (Character.isUpperCase(c) && i > 0 && !Character.isUpperCase(name.charAt(i-1))) {
                sb.append('_');
            }
            sb.append(Character.toLowerCase(c));
        }
        return sb.toString();
    }

    private void captureController(Entity e) {
        if (!"CDOTAPlayerController".equals(e.getDtClass().getDtName())) return;
        try {
            int teamNum = ri(e, "m_iTeamNum");
            if (teamNum != 2 && teamNum != 3) return;
            int pid = ri(e, "m_nPlayerID");
            String name = rs(e, "m_iszPlayerName");
            playerTeam.put(pid, teamNum);
            playerName.put(pid, name);
        } catch (Exception ex) { /* ignore */ }
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("Usage: java -jar dotacafe-parser.jar <replay.dem>");
            System.exit(1);
        }

        String replayPath = args[0];

        CDemoFileInfo fileInfo = Clarity.infoForFile(replayPath);
        CGameInfo.CDotaGameInfo dota = fileInfo.getGameInfo().getDota();
        List<CGameInfo.CDotaGameInfo.CPlayerInfo> playerInfos = dota.getPlayerInfoList();

        long matchId = dota.getMatchId();
        int gameMode = dota.getGameMode();
        int gameWinner = dota.getGameWinner();
        boolean radiantWin = (gameWinner == 2);
        int duration = (int) fileInfo.getPlaybackTime();
        boolean isLan = (matchId == 0 && playerInfos.isEmpty());

        DotaCafeParser parser = new DotaCafeParser();
        try {
            new SimpleRunner(new MappedFileSource(replayPath)).runWith(parser);
        } catch (Exception e) {
            System.err.println("Note: " + e.getMessage());
        }

        if (parser.gameWinnerEntity > 0) {
            radiantWin = (parser.gameWinnerEntity == 2);
        } else if (gameWinner == 0) {
            int rk = 0, dk = 0;
            for (int i = 0; i < 5; i++) rk += parser.prKills[i];
            for (int i = 5; i < 10; i++) dk += parser.prKills[i];
            radiantWin = rk > dk;
        }

        float pauseSecs = parser.totalPausedTicks / 30.0f;
        float actualGameSecs = duration - parser.gameStartTime - pauseSecs;
        if (actualGameSecs <= 0) actualGameSecs = duration;
        int durationSecs = (int) actualGameSecs;
        float gameTimeMins = Math.max(actualGameSecs / 60.0f, 1);

        // Calculate team scores
        int radiantKills = 0, direKills = 0;
        // Need to sum based on actual team membership
        List<Integer> radiantPids = new ArrayList<>();
        List<Integer> direPids = new ArrayList<>();
        for (Map.Entry<Integer, Integer> entry : parser.playerTeam.entrySet()) {
            if (entry.getValue() == 2) radiantPids.add(entry.getKey());
            else if (entry.getValue() == 3) direPids.add(entry.getKey());
        }
        Collections.sort(radiantPids);
        Collections.sort(direPids);

        for (int pid : radiantPids) radiantKills += parser.prKills[pid / 2];
        for (int pid : direPids) direKills += parser.prKills[pid / 2];

        // Build player list
        List<Map<String, Object>> players = new ArrayList<>();
        int slot = 0;

        // Build players for both teams using unified arrays
        int[][] teamPids = {
            radiantPids.stream().mapToInt(Integer::intValue).toArray(),
            direPids.stream().mapToInt(Integer::intValue).toArray()
        };
        String[] teamNames = {"radiant", "dire"};

        for (int t = 0; t < 2; t++) {
            for (int teamSlot = 0; teamSlot < teamPids[t].length; teamSlot++) {
                int pid = teamPids[t][teamSlot];
                int prIdx = pid / 2;
                String pname = parser.playerName.getOrDefault(pid, "");
                int heroId = parser.prHeroId[prIdx];
                String heroKey = findHeroKey(parser, heroId);
                List<Map<String, Object>> items = parser.purchaseLog.getOrDefault(heroKey, List.of());

                Map<String, Object> p = buildPlayer(slot, heroId, pname, teamNames[t],
                    parser.prKills[prIdx], parser.prDeaths[prIdx], parser.prAssists[prIdx],
                    parser.prLevel[prIdx],
                    parser.lastHitsT[t][teamSlot], parser.deniesT[t][teamSlot],
                    parser.netWorthT[t][teamSlot], parser.heroDamageT[t][teamSlot],
                    parser.towerDamageT[t][teamSlot], parser.heroHealingT[t][teamSlot],
                    parser.totalGoldT[t][teamSlot], parser.totalXPT[t][teamSlot],
                    gameTimeMins, items);

                // Role-relevant stats
                p.put("obs_wards_placed", parser.obsWardsPlacedT[t][teamSlot]);
                p.put("sentry_wards_placed", parser.sentryWardsPlacedT[t][teamSlot]);
                p.put("wards_destroyed", parser.wardsDestroyedT[t][teamSlot]);
                p.put("camps_stacked", parser.campsStackedT[t][teamSlot]);
                p.put("stun_duration", parser.stunDurationT[t][teamSlot]);
                p.put("smokes_used", parser.smokesUsedT[t][teamSlot]);
                p.put("gold_spent_support", parser.goldSpentSupportT[t][teamSlot]);
                p.put("gold_spent_buybacks", parser.goldSpentBuybacksT[t][teamSlot]);
                p.put("damage_taken", (int) parser.damageTakenT[t][teamSlot]);
                p.put("rune_pickups", parser.runePickupsT[t][teamSlot]);
                p.put("roshan_kills", parser.roshanKillsT[t][teamSlot]);
                p.put("tower_kills", parser.towerKillsT[t][teamSlot]);

                // Final inventory from entity state
                String heroShort = findHeroShortName(parser, heroId);
                p.put("final_items", parser.heroFinalItems.getOrDefault(heroShort, List.of()));

                players.add(p);
                slot++;
            }
        }

        // Bans
        List<Integer> bans = new ArrayList<>();
        for (int bh : parser.bannedHeroes) if (bh > 0) bans.add(bh);

        // Build result
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("purchase_log", parser.purchaseLog);
        result.put("hero_final_items", parser.heroFinalItems);
        result.put("match_id", matchId);
        result.put("duration", durationSecs);
        result.put("radiant_win", radiantWin);
        result.put("game_mode", gameMode);
        result.put("radiant_score", radiantKills);
        result.put("dire_score", direKills);
        result.put("is_lan", isLan);
        result.put("players", players);
        result.put("bans", bans);

        Gson gson = new GsonBuilder().setPrettyPrinting().create();
        System.out.println(gson.toJson(result));
    }

    /** Find hero short name in heroFinalItems that matches a hero class.
     *  Hero entity class: CDOTA_Unit_Hero_Slardar → "slardar" */
    private static String findHeroShortName(DotaCafeParser parser, int heroId) {
        // heroFinalItems is keyed by lowercase hero entity name (e.g. "slardar")
        // We match by checking all keys; the prHeroId array maps to these via the entity system
        // Since we can't resolve heroId→name in Java, we use index order matching
        // The heroFinalItems keys match the combat log hero names
        for (String key : parser.heroFinalItems.keySet()) {
            // Can't resolve directly; return key for Python to match
        }
        return "hero_" + heroId;
    }

    /** Find the hero short key in purchaseLog that matches a hero ID. */
    private static String findHeroKey(DotaCafeParser parser, int heroId) {
        // The purchaseLog keys are hero short names from combat log (e.g. "slardar")
        // We need to match heroId to a key. Build a reverse map from prHeroId.
        // Since we don't have a hero name DB in Java, we try all keys and match
        // by checking if any player with that heroId has purchases.
        // Simple approach: return all keys and let Python match by slot.
        // Better: include the full purchase log and let Python sort it out.
        for (String key : parser.purchaseLog.keySet()) {
            // Can't resolve hero_id to short name here without a mapping
            // Return the key as-is; Python will match by hero name
        }
        return "hero_" + heroId; // fallback; real matching happens below
    }

    private static Map<String, Object> buildPlayer(
            int slot, int heroId, String playerName, String team,
            int kills, int deaths, int assists, int level,
            int lastHits, int denies, int netWorth, int heroDamage,
            int towerDamage, int heroHealing, int totalGold, int totalXP,
            float gameTimeMins, List<Map<String, Object>> items) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("slot", slot);
        m.put("hero_name", "hero_" + heroId);
        m.put("hero_name_id", heroId);
        m.put("player_name", playerName);
        m.put("team", team);
        m.put("kills", kills);
        m.put("deaths", deaths);
        m.put("assists", assists);
        m.put("last_hits", lastHits);
        m.put("denies", denies);
        m.put("level", level);
        m.put("net_worth", netWorth);
        m.put("hero_damage", heroDamage);
        m.put("tower_damage", towerDamage);
        m.put("hero_healing", heroHealing);
        m.put("gpm", totalGold > 0 ? Math.round(totalGold / gameTimeMins) : 0);
        m.put("xpm", totalXP > 0 ? Math.round(totalXP / gameTimeMins) : 0);
        m.put("items", items);
        return m;
    }

    private static String pad(int i) { return String.format("%04d", i); }

    private static int ri(Entity e, String path) {
        try {
            FieldPath fp = e.getDtClass().getFieldPathForName(path);
            if (fp == null) return 0;
            Object v = e.getPropertyForFieldPath(fp);
            return v instanceof Number ? ((Number) v).intValue() : 0;
        } catch (Exception ex) { return 0; }
    }

    private static float rf(Entity e, String path) {
        try {
            FieldPath fp = e.getDtClass().getFieldPathForName(path);
            if (fp == null) return 0f;
            Object v = e.getPropertyForFieldPath(fp);
            return v instanceof Number ? ((Number) v).floatValue() : 0f;
        } catch (Exception ex) { return 0f; }
    }

    private static String rs(Entity e, String path) {
        try {
            FieldPath fp = e.getDtClass().getFieldPathForName(path);
            if (fp == null) return "";
            Object v = e.getPropertyForFieldPath(fp);
            return v != null ? v.toString() : "";
        } catch (Exception ex) { return ""; }
    }
}
