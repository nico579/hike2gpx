package org.hike2gpx.android;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.view.View;

import org.json.JSONArray;

/** Offline route overview; route and points remain visible without map tiles. */
final class RouteView extends View {
    private JSONArray route;
    private final Paint paint = new Paint(3);
    RouteView(Context context) { super(context); }
    void setRoute(JSONArray route) { this.route = route; invalidate(); }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        canvas.drawColor(Color.rgb(239, 246, 236));
        if (route == null || route.length() < 2) return;
        try {
            double minX = 180, maxX = -180, minY = 90, maxY = -90;
            for (int i = 0; i < route.length(); i++) {
                JSONArray p = route.getJSONArray(i);
                minX = Math.min(minX, p.getDouble(0)); maxX = Math.max(maxX, p.getDouble(0));
                minY = Math.min(minY, p.getDouble(1)); maxY = Math.max(maxY, p.getDouble(1));
            }
            double width = Math.max(maxX - minX, .0001), height = Math.max(maxY - minY, .0001);
            float scale = (float) Math.min((getWidth() - 40) / width, (getHeight() - 40) / height);
            Path path = new Path();
            for (int i = 0; i < route.length(); i++) {
                JSONArray p = route.getJSONArray(i);
                float x = 20 + (float) ((p.getDouble(0) - minX) * scale);
                float y = getHeight() - 20 - (float) ((p.getDouble(1) - minY) * scale);
                if (i == 0) path.moveTo(x, y); else path.lineTo(x, y);
            }
            paint.setColor(Color.rgb(20, 93, 203)); paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(6);
            canvas.drawPath(path, paint);
        } catch (Exception ignored) { }
    }
}
