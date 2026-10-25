package org.hike2gpx.android;

import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Point;

import org.json.JSONArray;
import org.json.JSONObject;
import org.osmdroid.util.GeoPoint;
import org.osmdroid.views.MapView;
import org.osmdroid.views.overlay.Overlay;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;

/** National paths from a verified zone package, visible even without a route or network. */
final class OfficialPathsOverlay extends Overlay {
    private final List<List<GeoPoint>> lines = new ArrayList<>();
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Point point = new Point();

    static OfficialPathsOverlay load(File directory) throws Exception {
        OfficialPathsOverlay overlay = new OfficialPathsOverlay();
        File file = new File(directory, "chemins-officiels.json");
        if (!file.isFile()) return overlay;
        JSONObject data = new JSONObject(new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8));
        JSONArray sections = data.getJSONArray("troncons");
        for (int i = 0; i < sections.length(); i++) {
            JSONArray points = sections.getJSONObject(i).getJSONArray("pts");
            List<GeoPoint> line = new ArrayList<>(points.length());
            for (int j = 0; j < points.length(); j++) {
                JSONArray pair = points.getJSONArray(j);
                line.add(new GeoPoint(pair.getDouble(0), pair.getDouble(1)));
            }
            if (line.size() >= 2) overlay.lines.add(line);
        }
        return overlay;
    }

    @Override public void draw(Canvas canvas, MapView map, boolean shadow) {
        if (shadow || map.getZoomLevelDouble() < 12) return;
        paint.setStyle(Paint.Style.STROKE);
        paint.setColor(Color.rgb(125, 31, 185));
        paint.setStrokeWidth(2.5f * map.getResources().getDisplayMetrics().density);
        Path path = new Path();
        for (List<GeoPoint> line : lines) {
            boolean first = true;
            for (GeoPoint vertex : line) {
                map.getProjection().toPixels(vertex, point);
                if (first) { path.moveTo(point.x, point.y); first = false; }
                else path.lineTo(point.x, point.y);
            }
        }
        canvas.drawPath(path, paint);
    }
}
