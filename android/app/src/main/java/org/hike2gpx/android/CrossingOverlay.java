package org.hike2gpx.android;

import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Point;

import org.json.JSONArray;
import org.json.JSONObject;
import org.osmdroid.util.GeoPoint;
import org.osmdroid.views.MapView;
import org.osmdroid.views.overlay.Overlay;

import java.util.ArrayList;
import java.util.List;

/** Obstacles from the downloaded zone, drawn independently of any route. */
final class CrossingOverlay extends Overlay {
    private static final class Crossing {
        final GeoPoint point;
        final boolean blocked;
        Crossing(GeoPoint point, boolean blocked) { this.point = point; this.blocked = blocked; }
    }
    private final List<Crossing> crossings = new ArrayList<>();
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Point point = new Point();

    void setManifest(JSONObject manifest) throws Exception {
        crossings.clear();
        JSONArray data = manifest.getJSONArray("franchissements");
        for (int i = 0; i < data.length(); i++) {
            JSONObject item = data.getJSONObject(i);
            crossings.add(new Crossing(new GeoPoint(item.getDouble("lat"), item.getDouble("lon")),
                    "blocked".equals(item.getString("statut"))));
        }
    }

    @Override public void draw(Canvas canvas, MapView map, boolean shadow) {
        if (shadow) return;
        float radius = 5f * map.getResources().getDisplayMetrics().density;
        for (Crossing crossing : crossings) {
            map.getProjection().toPixels(crossing.point, point);
            if (point.x < -radius || point.x > canvas.getWidth() + radius
                    || point.y < -radius || point.y > canvas.getHeight() + radius) continue;
            paint.setStyle(Paint.Style.FILL);
            paint.setColor(crossing.blocked ? Color.rgb(194, 31, 37) : Color.rgb(236, 155, 24));
            canvas.drawCircle(point.x, point.y, radius, paint);
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(2f);
            paint.setColor(Color.WHITE);
            canvas.drawCircle(point.x, point.y, radius, paint);
        }
    }
}
