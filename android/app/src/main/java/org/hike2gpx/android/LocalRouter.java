package org.hike2gpx.android;

import java.io.File;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import btools.router.FormatJson;
import btools.router.OsmNodeNamed;
import btools.router.OsmTrack;
import btools.router.RoutingContext;
import btools.router.RoutingEngine;
import btools.router.RoutingParamCollector;

/** BRouter 1.7.10 runs directly in this process against the downloaded RD5 files. */
final class LocalRouter {
    String calculate(File packageDir, String lonlats, String polylines) {
        RoutingParamCollector collector = new RoutingParamCollector();
        List<OsmNodeNamed> waypoints = collector.getWayPointList(lonlats);
        if (waypoints.size() < 2) throw new IllegalArgumentException("At least two points required");
        RoutingContext context = new RoutingContext();
        context.localFunction = new File(packageDir, "hike2gpx.brf").getAbsolutePath();
        Map<String, String> params = new HashMap<>();
        params.put("format", "json");
        params.put("alternativeidx", "0");
        if (polylines != null && !polylines.isEmpty()) params.put("polylines", polylines);
        collector.setParams(context, waypoints, params);
        RoutingEngine engine = new RoutingEngine(null, null, packageDir, waypoints, context);
        engine.quite = true;
        engine.doRun(60_000L);
        if (engine.getErrorMessage() != null) throw new IllegalStateException(engine.getErrorMessage());
        OsmTrack track = engine.getFoundTrack();
        if (track == null) throw new IllegalStateException("No route found");
        return new FormatJson(context).format(track);
    }
}
