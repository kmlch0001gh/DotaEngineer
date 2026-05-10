package cafe;

import skadistats.clarity.model.Entity;
import skadistats.clarity.model.FieldPath;
import skadistats.clarity.processor.entities.Entities;
import skadistats.clarity.processor.entities.OnEntityUpdated;
import skadistats.clarity.processor.runner.Context;
import skadistats.clarity.processor.runner.SimpleRunner;
import skadistats.clarity.source.MappedFileSource;

import java.util.*;

/**
 * Diagnostic tool: dumps PID-to-teamSlot mapping and m_vecDataTeam stats.
 */
public class EntityDumper {

    private boolean dumped = false;
    final Map<Integer, Integer> playerTeam = new HashMap<>();
    final Map<Integer, String> playerName = new HashMap<>();
    final int[] prHeroId = new int[20];
    final int[] prKills = new int[20];

    // DataTeam stats
    final int[][] netWorthT = new int[2][5];
    final int[][] lastHitsT = new int[2][5];
    final int[][] heroDamageT = new int[2][5];
    final int[][] totalGoldT = new int[2][5];

    // PlayerResource player-to-team-slot mapping
    final int[] prTeam = new int[20];
    final int[] prTeamSlot = new int[20];
    boolean controllerDumped = false;
    boolean prDumped = false;

    @OnEntityUpdated
    public void onUpdated(Context ctx, Entity e, FieldPath[] fps, int num) {
        try {
            String dt = e.getDtClass().getDtName();

            if ("CDOTAPlayerController".equals(dt)) {
                int teamNum = ri(e, "m_iTeamNum");
                if (teamNum != 2 && teamNum != 3) return;
                int pid = ri(e, "m_nPlayerID");
                String name = rs(e, "m_iszPlayerName");
                playerTeam.put(pid, teamNum);
                playerName.put(pid, name);
                // Dump ALL fields on first controller to find team member index
                if (!controllerDumped) {
                    controllerDumped = true;
                    System.out.println("=== CDOTAPlayerController fields (PID=" + pid + ") ===");
                    List<FieldPath> paths = e.getDtClass().collectFieldPaths(e.getState());
                    for (FieldPath fp : paths) {
                        try {
                            String fname = e.getDtClass().getNameForFieldPath(fp);
                            Object val = e.getPropertyForFieldPath(fp);
                            System.out.println("  " + fname + " = " + val);
                        } catch (Exception ex) {}
                    }
                }
            } else if ("CDOTA_PlayerResource".equals(dt) && !prDumped) {
                prDumped = true;
                // Dump all field names for first few players
                List<FieldPath> paths = e.getDtClass().collectFieldPaths(e.getState());
                Set<String> fieldNames = new TreeSet<>();
                for (FieldPath fp : paths) {
                    try {
                        String fname = e.getDtClass().getNameForFieldPath(fp);
                        if (fname.startsWith("m_vecPlayerTeamData.0000.")) {
                            fieldNames.add(fname.replace("m_vecPlayerTeamData.0000.", ""));
                        }
                    } catch (Exception ex) {}
                }
                System.out.println("=== PlayerResource fields per player ===");
                for (String f : fieldNames) System.out.println("  " + f);
            } else if ("CDOTA_PlayerResource".equals(dt)) {
                for (int i = 0; i < 20; i++) {
                    String p = "m_vecPlayerTeamData." + pad(i) + ".";
                    int hid = ri(e, p + "m_nSelectedHeroID");
                    if (hid > 0) prHeroId[i] = hid;
                    prKills[i] = ri(e, p + "m_iKills");
                    prTeam[i] = ri(e, p + "m_iTeam");
                    prTeamSlot[i] = ri(e, p + "m_iTeamSlot");
                }
            } else if ("CDOTA_DataRadiant".equals(dt) || "CDOTA_DataDire".equals(dt)) {
                int t = "CDOTA_DataRadiant".equals(dt) ? 0 : 1;
                for (int i = 0; i < 5; i++) {
                    String p = "m_vecDataTeam." + pad(i) + ".";
                    netWorthT[t][i] = ri(e, p + "m_iNetWorth");
                    lastHitsT[t][i] = ri(e, p + "m_iLastHitCount");
                    heroDamageT[t][i] = (int) rf(e, p + "m_flHeroDamage");
                    totalGoldT[t][i] = ri(e, p + "m_iTotalEarnedGold");
                }
            }

            if (!dumped && ctx.getTick() > 50000 && netWorthT[0][0] > 0) {
                dumped = true;
                dumpDiag();
            }
        } catch (Exception ex) {}
    }

    private void dumpDiag() {
        System.out.println("=== PID → Team Assignment ===");
        List<Integer> allPids = new ArrayList<>(playerTeam.keySet());
        Collections.sort(allPids);
        for (int pid : allPids) {
            int team = playerTeam.get(pid);
            int prIdx = pid / 2;
            System.out.printf("PID=%d team=%s name=%-15s heroId=%d kills=%d%n",
                pid, team == 2 ? "radiant" : "dire   ", playerName.get(pid), prHeroId[prIdx], prKills[prIdx]);
        }

        System.out.println("\n=== Radiant PIDs sorted ===");
        List<Integer> rPids = new ArrayList<>();
        List<Integer> dPids = new ArrayList<>();
        for (var e : playerTeam.entrySet()) {
            if (e.getValue() == 2) rPids.add(e.getKey());
            else dPids.add(e.getKey());
        }
        Collections.sort(rPids);
        Collections.sort(dPids);
        for (int i = 0; i < rPids.size(); i++) {
            int pid = rPids.get(i);
            System.out.printf("  teamSlot=%d → PID=%d heroId=%d%n", i, pid, prHeroId[pid/2]);
        }

        System.out.println("\n=== Dire PIDs sorted ===");
        for (int i = 0; i < dPids.size(); i++) {
            int pid = dPids.get(i);
            System.out.printf("  teamSlot=%d → PID=%d heroId=%d%n", i, pid, prHeroId[pid/2]);
        }

        System.out.println("\n=== m_vecDataTeam (Radiant) ===");
        for (int i = 0; i < 5; i++) {
            System.out.printf("  slot=%d NW=%d LH=%d HD=%d gold=%d%n",
                i, netWorthT[0][i], lastHitsT[0][i], heroDamageT[0][i], totalGoldT[0][i]);
        }

        System.out.println("\n=== m_vecDataTeam (Dire) ===");
        for (int i = 0; i < 5; i++) {
            System.out.printf("  slot=%d NW=%d LH=%d HD=%d gold=%d%n",
                i, netWorthT[1][i], lastHitsT[1][i], heroDamageT[1][i], totalGoldT[1][i]);
        }

        System.out.println("\n=== PlayerResource m_iTeam per prIdx ===");
        for (int i = 0; i < 12; i++) {
            if (prHeroId[i] > 0) {
                System.out.printf("  prIdx=%d heroId=%d m_iTeam=%d m_iTeamSlot=%d%n", i, prHeroId[i], prTeam[i], prTeamSlot[i]);
            }
        }

        System.exit(0);
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) { System.exit(1); }
        try {
            new SimpleRunner(new MappedFileSource(args[0])).runWith(new EntityDumper());
        } catch (Exception ex) {
            System.err.println("Error: " + ex.getMessage());
        }
    }

    private static String pad(int i) { return String.format("%04d", i); }
    private static int ri(Entity e, String path) {
        try { FieldPath fp = e.getDtClass().getFieldPathForName(path); if (fp == null) return 0; Object v = e.getPropertyForFieldPath(fp); return v instanceof Number ? ((Number)v).intValue() : 0; } catch (Exception ex) { return 0; }
    }
    private static float rf(Entity e, String path) {
        try { FieldPath fp = e.getDtClass().getFieldPathForName(path); if (fp == null) return 0f; Object v = e.getPropertyForFieldPath(fp); return v instanceof Number ? ((Number)v).floatValue() : 0f; } catch (Exception ex) { return 0f; }
    }
    private static String rs(Entity e, String path) {
        try { FieldPath fp = e.getDtClass().getFieldPathForName(path); if (fp == null) return ""; Object v = e.getPropertyForFieldPath(fp); return v != null ? v.toString() : ""; } catch (Exception ex) { return ""; }
    }
}
