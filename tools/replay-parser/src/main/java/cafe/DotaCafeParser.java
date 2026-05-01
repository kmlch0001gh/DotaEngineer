package cafe;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import skadistats.clarity.Clarity;
import skadistats.clarity.model.Entity;
import skadistats.clarity.model.FieldPath;
import skadistats.clarity.processor.entities.Entities;
import skadistats.clarity.processor.entities.OnEntityCreated;
import skadistats.clarity.processor.entities.OnEntityUpdated;
import skadistats.clarity.processor.runner.Context;
import skadistats.clarity.processor.runner.SimpleRunner;
import skadistats.clarity.source.MappedFileSource;
import skadistats.clarity.wire.shared.demo.proto.Demo.CDemoFileInfo;
import skadistats.clarity.wire.shared.demo.proto.Demo.CGameInfo;

import java.util.*;

/**
 * Parses a Dota 2 .dem replay and outputs JSON with full match data.
 *
 * Data comes from 3 entity types:
 * - CDOTAPlayerController: playerID, team (2=R, 3=D), player name
 * - CDOTA_PlayerResource.m_vecPlayerTeamData[playerID/2]: KDA, level, heroID
 * - CDOTA_DataRadiant/Dire.m_vecDataTeam[team_slot]: NW, LH, GPM, damage
 *
 * The tricky part is mapping between these. Each CDOTAPlayerController has
 * a m_nPlayerID; dividing by 2 gives the index into m_vecPlayerTeamData.
 * Within each team, the team_slot order in m_vecDataTeam corresponds to
 * the order controllers appear for that team (sorted by playerID).
 */
public class DotaCafeParser {

    // Per-player stats from CDOTA_PlayerResource (indexed by playerID/2)
    final int[] prKills = new int[20];
    final int[] prDeaths = new int[20];
    final int[] prAssists = new int[20];
    final int[] prLevel = new int[20];
    final int[] prHeroId = new int[20];

    // Per-team-slot stats from CDOTA_DataRadiant (indexed 0-4)
    final int[] radNetWorth = new int[5];
    final int[] radLastHits = new int[5];
    final int[] radDenies = new int[5];
    final int[] radHeroDamage = new int[5];
    final int[] radTowerDamage = new int[5];
    final int[] radHeroHealing = new int[5];
    final int[] radTotalGold = new int[5];
    final int[] radTotalXP = new int[5];

    // Per-team-slot stats from CDOTA_DataDire (indexed 0-4)
    final int[] direNetWorth = new int[5];
    final int[] direLastHits = new int[5];
    final int[] direDenies = new int[5];
    final int[] direHeroDamage = new int[5];
    final int[] direTowerDamage = new int[5];
    final int[] direHeroHealing = new int[5];
    final int[] direTotalGold = new int[5];
    final int[] direTotalXP = new int[5];

    // Team scores from CDOTATeam
    int radiantHeroKills = 0;
    int direHeroKills = 0;

    float gameTime = 0;
    float gameStartTime = 0;
    int totalPausedTicks = 0;
    int gameWinnerEntity = 0;
    final int[] bannedHeroes = new int[24]; // up to 24 bans in CM

    // Controller info: playerID → {teamNum, playerName}
    // Collected via OnEntityCreated + OnEntityUpdated
    final Map<Integer, Integer> playerTeam = new HashMap<>();   // playerID → 2 or 3
    final Map<Integer, String> playerName = new HashMap<>();    // playerID → name

    @OnEntityCreated
    public void onCreated(Context ctx, Entity e) {
        captureController(e);
    }

    @OnEntityUpdated
    public void onUpdated(Context ctx, Entity e, FieldPath[] fps, int num) {
        try {
            String dt = e.getDtClass().getDtName();

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
            } else if ("CDOTA_DataRadiant".equals(dt)) {
                for (int i = 0; i < 5; i++) {
                    String p = "m_vecDataTeam." + pad(i) + ".";
                    radNetWorth[i] = ri(e, p + "m_iNetWorth");
                    radLastHits[i] = ri(e, p + "m_iLastHitCount");
                    radDenies[i] = ri(e, p + "m_iDenyCount");
                    radHeroDamage[i] = (int) rf(e, p + "m_flHeroDamage");
                    radTowerDamage[i] = (int) rf(e, p + "m_flTowerDamage");
                    radHeroHealing[i] = (int) rf(e, p + "m_flHeroHealing");
                    radTotalGold[i] = ri(e, p + "m_iTotalEarnedGold");
                    radTotalXP[i] = ri(e, p + "m_iTotalEarnedXP");
                }
            } else if ("CDOTA_DataDire".equals(dt)) {
                for (int i = 0; i < 5; i++) {
                    String p = "m_vecDataTeam." + pad(i) + ".";
                    direNetWorth[i] = ri(e, p + "m_iNetWorth");
                    direLastHits[i] = ri(e, p + "m_iLastHitCount");
                    direDenies[i] = ri(e, p + "m_iDenyCount");
                    direHeroDamage[i] = (int) rf(e, p + "m_flHeroDamage");
                    direTowerDamage[i] = (int) rf(e, p + "m_flTowerDamage");
                    direHeroHealing[i] = (int) rf(e, p + "m_flHeroHealing");
                    direTotalGold[i] = ri(e, p + "m_iTotalEarnedGold");
                    direTotalXP[i] = ri(e, p + "m_iTotalEarnedXP");
                }
            } else if ("CDOTATeam".equals(dt)) {
                int teamNum = ri(e, "m_iTeamNum");
                int hk = ri(e, "m_iHeroKills");
                if (teamNum == 2) radiantHeroKills = hk;
                else if (teamNum == 3) direHeroKills = hk;
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

    private void captureController(Entity e) {
        if (!"CDOTAPlayerController".equals(e.getDtClass().getDtName())) return;
        try {
            int teamNum = ri(e, "m_iTeamNum");
            if (teamNum != 2 && teamNum != 3) return; // skip spectators
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

        // Basic info from CDemoFileInfo
        CDemoFileInfo fileInfo = Clarity.infoForFile(replayPath);
        CGameInfo.CDotaGameInfo dota = fileInfo.getGameInfo().getDota();
        List<CGameInfo.CDotaGameInfo.CPlayerInfo> playerInfos = dota.getPlayerInfoList();

        long matchId = dota.getMatchId();
        int gameMode = dota.getGameMode();
        int gameWinner = dota.getGameWinner();
        boolean radiantWin = (gameWinner == 2);
        int duration = (int) fileInfo.getPlaybackTime();
        boolean isLan = (matchId == 0 && playerInfos.isEmpty());

        // Process full replay
        DotaCafeParser parser = new DotaCafeParser();
        try {
            new SimpleRunner(new MappedFileSource(replayPath)).runWith(parser);
        } catch (Exception e) {
            System.err.println("Note: " + e.getMessage());
        }

        // Determine winner
        if (parser.gameWinnerEntity > 0) {
            radiantWin = (parser.gameWinnerEntity == 2);
        } else if (gameWinner == 0) {
            radiantWin = parser.radiantHeroKills > parser.direHeroKills;
        }

        // playback_time includes pre-game pick phase + pauses
        // actual game duration = playback_time - gameStartTime - pauses
        float pauseSecs = parser.totalPausedTicks / 30.0f; // ticks are 1/30s
        float actualGameSecs = duration - parser.gameStartTime - pauseSecs;
        if (actualGameSecs <= 0) actualGameSecs = duration; // fallback
        int durationSecs = (int) actualGameSecs;
        float gameTimeMins = Math.max(actualGameSecs / 60.0f, 1);

        // Build player list
        List<Map<String, Object>> players = new ArrayList<>();

        if (!playerInfos.isEmpty()) {
            // Online replay — CDemoFileInfo has everything
            for (int i = 0; i < Math.min(playerInfos.size(), 10); i++) {
                CGameInfo.CDotaGameInfo.CPlayerInfo pi = playerInfos.get(i);
                int prIdx = i; // for online replays, index matches
                String team = pi.getGameTeam() == 2 ? "radiant" : "dire";
                players.add(buildPlayerOnline(i, pi.getHeroName(), pi.getPlayerName(),
                    team, prIdx, parser, gameTimeMins));
            }
        } else {
            // LAN replay — must cross-reference controllers with entity data
            // Sort controllers by playerID within each team
            List<Integer> radiantPids = new ArrayList<>();
            List<Integer> direPids = new ArrayList<>();
            for (Map.Entry<Integer, Integer> entry : parser.playerTeam.entrySet()) {
                if (entry.getValue() == 2) radiantPids.add(entry.getKey());
                else if (entry.getValue() == 3) direPids.add(entry.getKey());
            }
            Collections.sort(radiantPids);
            Collections.sort(direPids);

            int slot = 0;

            // Radiant players
            for (int teamSlot = 0; teamSlot < radiantPids.size(); teamSlot++) {
                int pid = radiantPids.get(teamSlot);
                int prIdx = pid / 2; // index into m_vecPlayerTeamData
                String name = parser.playerName.getOrDefault(pid, "");
                Map<String, Object> p = new LinkedHashMap<>();
                p.put("slot", slot);
                p.put("hero_name", "hero_" + parser.prHeroId[prIdx]);
                p.put("hero_name_id", parser.prHeroId[prIdx]);
                p.put("player_name", name);
                p.put("team", "radiant");
                p.put("kills", parser.prKills[prIdx]);
                p.put("deaths", parser.prDeaths[prIdx]);
                p.put("assists", parser.prAssists[prIdx]);
                p.put("last_hits", parser.radLastHits[teamSlot]);
                p.put("denies", parser.radDenies[teamSlot]);
                p.put("level", parser.prLevel[prIdx]);
                p.put("net_worth", parser.radNetWorth[teamSlot]);
                p.put("hero_damage", parser.radHeroDamage[teamSlot]);
                p.put("tower_damage", parser.radTowerDamage[teamSlot]);
                p.put("hero_healing", parser.radHeroHealing[teamSlot]);
                p.put("gpm", parser.radTotalGold[teamSlot] > 0 ?
                    Math.round(parser.radTotalGold[teamSlot] / gameTimeMins) : 0);
                p.put("xpm", parser.radTotalXP[teamSlot] > 0 ?
                    Math.round(parser.radTotalXP[teamSlot] / gameTimeMins) : 0);
                players.add(p);
                slot++;
            }

            // Dire players
            for (int teamSlot = 0; teamSlot < direPids.size(); teamSlot++) {
                int pid = direPids.get(teamSlot);
                int prIdx = pid / 2;
                String name = parser.playerName.getOrDefault(pid, "");
                Map<String, Object> p = new LinkedHashMap<>();
                p.put("slot", slot);
                p.put("hero_name", "hero_" + parser.prHeroId[prIdx]);
                p.put("hero_name_id", parser.prHeroId[prIdx]);
                p.put("player_name", name);
                p.put("team", "dire");
                p.put("kills", parser.prKills[prIdx]);
                p.put("deaths", parser.prDeaths[prIdx]);
                p.put("assists", parser.prAssists[prIdx]);
                p.put("last_hits", parser.direLastHits[teamSlot]);
                p.put("denies", parser.direDenies[teamSlot]);
                p.put("level", parser.prLevel[prIdx]);
                p.put("net_worth", parser.direNetWorth[teamSlot]);
                p.put("hero_damage", parser.direHeroDamage[teamSlot]);
                p.put("tower_damage", parser.direTowerDamage[teamSlot]);
                p.put("hero_healing", parser.direHeroHealing[teamSlot]);
                p.put("gpm", parser.direTotalGold[teamSlot] > 0 ?
                    Math.round(parser.direTotalGold[teamSlot] / gameTimeMins) : 0);
                p.put("xpm", parser.direTotalXP[teamSlot] > 0 ?
                    Math.round(parser.direTotalXP[teamSlot] / gameTimeMins) : 0);
                players.add(p);
                slot++;
            }
        }

        // Build result
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("match_id", matchId);
        result.put("duration", durationSecs);
        result.put("radiant_win", radiantWin);
        result.put("game_mode", gameMode);
        result.put("radiant_score", parser.radiantHeroKills);
        result.put("dire_score", parser.direHeroKills);
        result.put("is_lan", isLan);
        result.put("players", players);

        // Banned heroes (non-zero IDs)
        List<Integer> bans = new ArrayList<>();
        for (int bh : parser.bannedHeroes) {
            if (bh > 0) bans.add(bh);
        }
        result.put("bans", bans);

        Gson gson = new GsonBuilder().setPrettyPrinting().create();
        System.out.println(gson.toJson(result));
    }

    private static Map<String, Object> buildPlayerOnline(int slot, String heroName,
            String playerName, String team, int prIdx, DotaCafeParser p, float durMins) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("slot", slot);
        m.put("hero_name", heroName);
        m.put("hero_name_id", p.prHeroId[prIdx]);
        m.put("player_name", playerName);
        m.put("team", team);
        m.put("kills", p.prKills[prIdx]);
        m.put("deaths", p.prDeaths[prIdx]);
        m.put("assists", p.prAssists[prIdx]);
        m.put("last_hits", p.radLastHits[0]); // TODO: fix for online
        m.put("denies", p.radDenies[0]);
        m.put("level", p.prLevel[prIdx]);
        m.put("net_worth", 0);
        m.put("hero_damage", 0);
        m.put("tower_damage", 0);
        m.put("hero_healing", 0);
        m.put("gpm", 0);
        m.put("xpm", 0);
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
