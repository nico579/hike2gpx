package org.hike2gpx.android;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;

import javax.net.ssl.HttpsURLConnection;

/** Explicit server fallback. Normal Android routing never calls this endpoint. */
final class RemoteRouter {
    JSONObject calculate(String server, double[] a, double[] b, String source, boolean strict) throws Exception {
        if (!server.matches("https://[^/?#@]+")) throw new IllegalArgumentException("HTTPS server address required");
        JSONObject request = new JSONObject();
        request.put("points", new JSONArray().put(new JSONArray().put(a[0]).put(a[1]))
                .put(new JSONArray().put(b[0]).put(b[1])));
        request.put("source", source);
        request.put("ign", true);
        request.put("strict", strict);
        request.put("comparer", false);
        HttpsURLConnection connection = (HttpsURLConnection) new URL(server + "/api/itineraire").openConnection();
        connection.setRequestMethod("POST");
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setConnectTimeout(10_000);
        connection.setReadTimeout(180_000);
        connection.setDoOutput(true);
        try {
            byte[] payload = request.toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream out = connection.getOutputStream()) { out.write(payload); }
            if (connection.getResponseCode() != 200) throw new IllegalStateException("HTTP " + connection.getResponseCode());
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream in = connection.getInputStream()) {
                byte[] block = new byte[8192];
                for (int count; (count = in.read(block)) != -1;) {
                    bytes.write(block, 0, count);
                    if (bytes.size() > 32 * 1024 * 1024) throw new IllegalStateException("Route response too large");
                }
            }
            JSONObject result = new JSONObject(new String(bytes.toByteArray(), StandardCharsets.UTF_8));
            if (result.has("erreur")) throw new IllegalStateException(result.getString("erreur"));
            return result.getJSONObject("itineraire");
        } finally { connection.disconnect(); }
    }
}
