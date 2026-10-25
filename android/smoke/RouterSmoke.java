package org.hike2gpx.android;

import java.io.File;

/** Run the exact Android local-routing adapter with an already installed RD5. */
public final class RouterSmoke {
    public static void main(String[] args) {
        if (args.length != 1) throw new IllegalArgumentException("Expected package directory");
        String geojson = new LocalRouter().calculate(new File(args[0]),
                "6.045000,43.458000|6.050000,43.462000", "", 256);
        if (!geojson.contains("\"FeatureCollection\"") || !geojson.contains("\"LineString\""))
            throw new IllegalStateException("Unexpected BRouter route");
        System.out.println("Local BRouter route OK: " + geojson.length() + " JSON chars");
    }
}
