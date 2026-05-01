package cafe;

import skadistats.clarity.model.Entity;
import skadistats.clarity.model.FieldPath;
import skadistats.clarity.processor.entities.Entities;
import skadistats.clarity.processor.entities.OnEntityUpdated;
import skadistats.clarity.processor.runner.Context;
import skadistats.clarity.processor.runner.SimpleRunner;
import skadistats.clarity.source.MappedFileSource;

import java.util.*;

public class EntityDumper {

    private boolean dumped = false;

    @OnEntityUpdated
    public void onUpdated(Context ctx, Entity e, FieldPath[] fps, int num) {
        if (dumped) return;
        if (ctx.getTick() < 50000) return;
        String dt = e.getDtClass().getDtName();
        if (!"CDOTAGamerulesProxy".equals(dt)) return;

        dumped = true;
        System.out.println("=== CDOTAGamerulesProxy at tick " + ctx.getTick() + " ===");
        List<FieldPath> paths = e.getDtClass().collectFieldPaths(e.getState());
        for (FieldPath fp : paths) {
            try {
                String name = e.getDtClass().getNameForFieldPath(fp);
                if (name.contains("Time") || name.contains("time")
                    || name.contains("Clock") || name.contains("Start")
                    || name.contains("Duration") || name.contains("Game")) {
                    Object val = e.getPropertyForFieldPath(fp);
                    System.out.println("  " + name + " = " + val);
                }
            } catch (Exception ex) {}
        }
        System.exit(0);
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) { System.exit(1); }
        try {
            new SimpleRunner(new MappedFileSource(args[0])).runWith(new EntityDumper());
        } catch (Exception e) {}
    }
}
