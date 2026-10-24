package org.hike2gpx.android;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.ArrayAdapter;
import android.widget.Switch;
import android.widget.TextView;

import org.osmdroid.config.Configuration;
import org.osmdroid.events.MapEventsReceiver;
import org.osmdroid.util.BoundingBox;
import org.osmdroid.util.GeoPoint;
import org.osmdroid.views.MapView;
import org.osmdroid.views.overlay.MapEventsOverlay;
import org.osmdroid.views.overlay.Polyline;
import org.osmdroid.views.overlay.CopyrightOverlay;

import org.json.JSONArray;
import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final String[] SOURCES = {"ign", "atkis", "swisstlm3d", "zabaged", "bdot10k_ds"};
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private EditText server, bounds, start, finish;
    private Spinner source;
    private Switch strict;
    private TextView status;
    private MapView map;
    private Polyline routeOverlay;
    private CrossingOverlay crossingOverlay;
    private boolean nextTapIsStart = true;
    private JSONObject lastRoute;
    private PackageStore packages;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        Configuration.getInstance().setUserAgentValue("hike2gpx-android/0.1 (+https://github.com/nico579/hike2gpx)");
        Configuration.getInstance().setOsmdroidBasePath(new java.io.File(getCacheDir(), "osmdroid"));
        Configuration.getInstance().setOsmdroidTileCache(new java.io.File(getCacheDir(), "osmdroid/tiles"));
        packages = new PackageStore(this);
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (12 * getResources().getDisplayMetrics().density);
        column.setPadding(pad, pad, pad, pad);
        ScrollView scroll = new ScrollView(this);
        scroll.addView(column);
        setContentView(scroll);
        TextView title = new TextView(this);
        title.setText("hike2gpx"); title.setTextSize(24);
        column.addView(title);
        server = field(column, R.string.server, "https://rando.example.org");
        server.setText(getPreferences(0).getString("server", ""));
        source = new Spinner(this);
        source.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, SOURCES));
        column.addView(source);
        bounds = field(column, R.string.zone, "43.42, 5.98, 43.49, 6.08");
        start = field(column, R.string.start, "43.458, 6.045");
        finish = field(column, R.string.finish, "43.465, 6.055");
        strict = new Switch(this);
        strict.setText(R.string.strict);
        strict.setChecked(true);
        column.addView(strict);
        Button download = button(column, R.string.download);
        Button visibleZone = button(column, R.string.visible_zone);
        Button calculate = button(column, R.string.calculate);
        Button serverFallback = button(column, R.string.server_fallback);
        Button export = button(column, R.string.export);
        status = new TextView(this);
        status.setText(R.string.status_ready);
        column.addView(status);
        map = new MapView(this);
        map.setMultiTouchControls(true);
        map.getController().setZoom(13.0);
        map.getController().setCenter(new GeoPoint(43.458, 6.045));
        map.getOverlays().add(new CopyrightOverlay(this));
        crossingOverlay = new CrossingOverlay();
        map.getOverlays().add(crossingOverlay);
        map.getOverlays().add(new MapEventsOverlay(new MapEventsReceiver() {
            @Override public boolean singleTapConfirmedHelper(GeoPoint point) {
                EditText target = nextTapIsStart ? start : finish;
                target.setText(String.format(Locale.US, "%.6f, %.6f", point.getLatitude(), point.getLongitude()));
                nextTapIsStart = !nextTapIsStart;
                return true;
            }
            @Override public boolean longPressHelper(GeoPoint point) { return false; }
        }));
        column.addView(map, new LinearLayout.LayoutParams(-1, (int) (350 * getResources().getDisplayMetrics().density)));
        visibleZone.setOnClickListener(v -> {
            BoundingBox box = map.getBoundingBox();
            bounds.setText(String.format(Locale.US, "%.6f, %.6f, %.6f, %.6f",
                    box.getLatSouth(), box.getLonWest(), box.getLatNorth(), box.getLonEast()));
        });
        download.setOnClickListener(v -> {
            String areaText = bounds.getText().toString();
            String address = server.getText().toString().trim().replaceAll("/+$", "");
            String selected = selectedSource();
            boolean useStrict = strict.isChecked();
            getPreferences(0).edit().putString("server", address).apply();
            runTask(() -> {
                double[] area = numbers(areaText, 4);
                PackageStore.Zone zone = packages.download(address, area, selected, useStrict);
                runOnUiThread(() -> showCrossings(zone.manifest));
                return getString(R.string.zone_ready, zone.manifest.getJSONArray("segments").length());
            });
        });
        calculate.setOnClickListener(v -> {
            String startText = start.getText().toString(), finishText = finish.getText().toString();
            String selected = selectedSource();
            boolean useStrict = strict.isChecked();
            runTask(() -> {
            double[] a = numbers(startText, 2);
            double[] b = numbers(finishText, 2);
            double[] area = {Math.min(a[0], b[0]), Math.min(a[1], b[1]),
                    Math.max(a[0], b[0]), Math.max(a[1], b[1])};
            PackageStore.Zone zone = packages.covering(area, selected, useStrict);
            if (zone == null) throw new IllegalStateException(getString(R.string.zone_missing));
            runOnUiThread(() -> showCrossings(zone.manifest));
            String lonlats = String.format(Locale.US, "%.7f,%.7f|%.7f,%.7f", a[1], a[0], b[1], b[0]);
            String result = new LocalRouter().calculate(zone.directory, lonlats,
                    zone.manifest.getString("polylines"));
            JSONObject geojson = new JSONObject(result);
            JSONObject feature = geojson.has("features") ? geojson.getJSONArray("features").getJSONObject(0) : geojson;
            JSONArray coordinates = feature.getJSONObject("geometry").getJSONArray("coordinates");
            verifyRoute(coordinates, zone.manifest, useStrict);
            runOnUiThread(() -> { lastRoute = feature; showRoute(coordinates); });
            return getString(R.string.route_ready, coordinates.length());
            });
        });
        serverFallback.setOnClickListener(v -> {
            String address = server.getText().toString().trim().replaceAll("/+$", "");
            String startText = start.getText().toString(), finishText = finish.getText().toString();
            String selected = selectedSource();
            boolean useStrict = strict.isChecked();
            runTask(() -> {
                JSONObject feature = new RemoteRouter().calculate(address, numbers(startText, 2),
                        numbers(finishText, 2), selected, useStrict);
                JSONArray coordinates = feature.getJSONObject("geometry").getJSONArray("coordinates");
                runOnUiThread(() -> { lastRoute = feature; showRoute(coordinates); });
                return getString(R.string.route_remote, coordinates.length());
            });
        });
        export.setOnClickListener(v -> {
            if (lastRoute == null) { status.setText(R.string.no_route); return; }
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            intent.setType("application/gpx+xml");
            intent.putExtra(Intent.EXTRA_TITLE, "hike2gpx.gpx");
            startActivityForResult(intent, 1);
        });
    }

    private EditText field(LinearLayout parent, int label, String hint) {
        TextView caption = new TextView(this); caption.setText(label); parent.addView(caption);
        EditText value = new EditText(this); value.setSingleLine(true); value.setHint(hint); parent.addView(value);
        return value;
    }

    private Button button(LinearLayout parent, int label) {
        Button value = new Button(this); value.setText(label); parent.addView(value); return value;
    }

    private String selectedSource() { return SOURCES[source.getSelectedItemPosition()]; }

    private void showCrossings(JSONObject manifest) {
        try { crossingOverlay.setManifest(manifest); map.invalidate(); }
        catch (Exception error) { status.setText(error.getMessage()); }
    }

    private void showRoute(JSONArray coordinates) {
        try {
            if (routeOverlay != null) map.getOverlays().remove(routeOverlay);
            List<GeoPoint> points = new ArrayList<>();
            double south = 90, west = 180, north = -90, east = -180;
            for (int i = 0; i < coordinates.length(); i++) {
                JSONArray item = coordinates.getJSONArray(i);
                double lat = item.getDouble(1), lon = item.getDouble(0);
                points.add(new GeoPoint(lat, lon));
                south = Math.min(south, lat); west = Math.min(west, lon);
                north = Math.max(north, lat); east = Math.max(east, lon);
            }
            routeOverlay = new Polyline(map);
            routeOverlay.setPoints(points);
            routeOverlay.getOutlinePaint().setColor(0xff175dcb);
            routeOverlay.getOutlinePaint().setStrokeWidth(8f);
            map.getOverlays().add(routeOverlay);
            map.zoomToBoundingBox(new BoundingBox(north, east, south, west), true, 40);
            map.invalidate();
        } catch (Exception error) { status.setText(error.getMessage()); }
    }

    private static double[] numbers(String value, int count) {
        String[] fields = value.trim().split("[,; ]+");
        if (fields.length != count) throw new IllegalArgumentException("Expected " + count + " coordinates");
        double[] result = new double[count];
        for (int i = 0; i < count; i++) result[i] = Double.parseDouble(fields[i]);
        return result;
    }

    private interface Work { String execute() throws Exception; }
    private void runTask(Work work) {
        status.setText(R.string.status_working);
        worker.execute(() -> {
            try { String message = work.execute(); runOnUiThread(() -> status.setText(message)); }
            catch (Exception error) { runOnUiThread(() -> status.setText(error.getMessage())); }
        });
    }

    private static void verifyRoute(JSONArray coords, JSONObject manifest, boolean strict) throws Exception {
        JSONArray coverage = manifest.getJSONArray("couverture");
        for (int i = 0; i < coords.length(); i++) {
            JSONArray point = coords.getJSONArray(i);
            double lon = point.getDouble(0), lat = point.getDouble(1);
            if (lat < coverage.getDouble(0) - .002 || lon < coverage.getDouble(1) - .002
                    || lat > coverage.getDouble(2) + .002 || lon > coverage.getDouble(3) + .002)
                throw new IllegalStateException("Route leaves the downloaded zone");
        }
        JSONArray crossings = manifest.getJSONArray("franchissements");
        for (int i = 0; i < crossings.length(); i++) {
            JSONObject crossing = crossings.getJSONObject(i);
            if (!crossing.getString("statut").equals("blocked") && !strict) continue;
            JSONArray cuts = crossing.getJSONArray("coupes");
            for (int j = 0; j < cuts.length(); j++) {
                JSONArray cut = cuts.getJSONArray(j);
                double[] c = pair(cut.getJSONArray(0)), d = pair(cut.getJSONArray(1));
                for (int k = 1; k < coords.length(); k++) {
                    if (intersects(pair(coords.getJSONArray(k - 1)), pair(coords.getJSONArray(k)), c, d))
                        throw new IllegalStateException("Route crosses a forbidden barrier");
                }
            }
        }
    }

    private static double[] pair(JSONArray array) throws Exception {
        return new double[]{array.getDouble(0), array.getDouble(1)};
    }
    private static double cross(double[] a, double[] b, double[] c) {
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    }
    private static boolean intersects(double[] a, double[] b, double[] c, double[] d) {
        double abC = cross(a, b, c), abD = cross(a, b, d);
        double cdA = cross(c, d, a), cdB = cross(c, d, b);
        if (abC * abD < 0 && cdA * cdB < 0) return true;
        return touches(a, b, c, abC) || touches(a, b, d, abD)
                || touches(c, d, a, cdA) || touches(c, d, b, cdB);
    }
    private static boolean touches(double[] a, double[] b, double[] p, double side) {
        return Math.abs(side) < 1e-13 && p[0] >= Math.min(a[0], b[0]) - 1e-9
                && p[0] <= Math.max(a[0], b[0]) + 1e-9
                && p[1] >= Math.min(a[1], b[1]) - 1e-9
                && p[1] <= Math.max(a[1], b[1]) + 1e-9;
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != 1 || result != RESULT_OK || data == null || lastRoute == null) return;
        try (java.io.OutputStream out = getContentResolver().openOutputStream(data.getData())) {
            JSONArray coordinates = lastRoute.getJSONObject("geometry").getJSONArray("coordinates");
            StringBuilder gpx = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?><gpx version=\"1.1\" creator=\"hike2gpx\" xmlns=\"http://www.topografix.com/GPX/1/1\"><trk><name>hike2gpx</name><trkseg>");
            for (int i = 0; i < coordinates.length(); i++) {
                JSONArray p = coordinates.getJSONArray(i);
                gpx.append("<trkpt lat=\"").append(p.getDouble(1)).append("\" lon=\"").append(p.getDouble(0)).append("\">");
                if (p.length() > 2) gpx.append("<ele>").append(p.getDouble(2)).append("</ele>");
                gpx.append("</trkpt>");
            }
            out.write(gpx.append("</trkseg></trk></gpx>").toString().getBytes(StandardCharsets.UTF_8));
            status.setText(R.string.export_done);
        } catch (Exception error) { status.setText(error.getMessage()); }
    }

    @Override protected void onResume() { super.onResume(); map.onResume(); }
    @Override protected void onPause() { map.onPause(); super.onPause(); }
    @Override protected void onDestroy() { worker.shutdownNow(); map.onDetach(); super.onDestroy(); }
}
