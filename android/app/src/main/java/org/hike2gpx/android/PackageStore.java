package org.hike2gpx.android;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;

import javax.net.ssl.HttpsURLConnection;

/** Downloads precomputed zones; cached files are usable with no network. */
final class PackageStore {
    private final File root;

    PackageStore(Context context) {
        root = new File(context.getFilesDir(), "zones");
        if (!root.exists() && !root.mkdirs()) throw new IllegalStateException("Cannot create zone directory");
    }

    static final class Zone {
        final File directory;
        final JSONObject manifest;
        Zone(File directory, JSONObject manifest) { this.directory = directory; this.manifest = manifest; }
    }

    List<Zone> installed() throws Exception {
        List<Zone> found = new ArrayList<>();
        File[] directories = root.listFiles();
        if (directories == null) return found;
        for (File dir : directories) {
            File manifest = new File(dir, "manifest.json");
            if (!dir.isDirectory() || !manifest.isFile()) continue;
            try {
                JSONObject json = new JSONObject(new String(readAll(manifest), StandardCharsets.UTF_8));
                if (json.optInt("format") == 1 && json.optBoolean("pret") && filesValid(dir, json))
                    found.add(new Zone(dir, json));
            } catch (Exception ignored) { /* paquet incomplet : les autres zones restent disponibles */ }
        }
        return found;
    }

    Zone covering(double[] bounds, String source, boolean strict) throws Exception {
        File[] directories = root.listFiles();
        if (directories == null) return null;
        for (File dir : directories) {
            File file = new File(dir, "manifest.json");
            if (!dir.isDirectory() || !file.isFile()) continue;
            try {
                JSONObject json = new JSONObject(new String(readAll(file), StandardCharsets.UTF_8));
                if (json.optInt("format") != 1 || !json.optBoolean("pret")
                        || !source.equals(json.optString("source")) || json.optBoolean("strict") != strict) continue;
                JSONArray area = json.getJSONArray("couverture");
                if (area.getDouble(0) <= bounds[0] && area.getDouble(1) <= bounds[1]
                        && area.getDouble(2) >= bounds[2] && area.getDouble(3) >= bounds[3]
                        && filesValid(dir, json)) return new Zone(dir, json);
            } catch (Exception ignored) { /* autre paquet endommagé : poursuivre la recherche */ }
        }
        return null;
    }

    Zone download(String server, double[] bounds, String source, boolean strict) throws Exception {
        if (!server.matches("https://[^/?#@]+")) throw new IllegalArgumentException("HTTPS server address required");
        String query = String.format(java.util.Locale.US,
                "/api/paquet-zone?s=%.7f&w=%.7f&n=%.7f&e=%.7f&source=%s&strict=%d&officiel=1",
                bounds[0], bounds[1], bounds[2], bounds[3], source, strict ? 1 : 0);
        JSONObject manifest = new JSONObject(new String(fetch(server + query), StandardCharsets.UTF_8));
        if (!manifest.optBoolean("pret") || manifest.optInt("format") != 1) {
            throw new IllegalStateException("This zone has not been prepared on the server");
        }
        String id = hex(MessageDigest.getInstance("SHA-256").digest(query.getBytes(StandardCharsets.UTF_8))).substring(0, 24);
        File dir = new File(root, id);
        if (!dir.exists() && !dir.mkdirs()) throw new IllegalStateException("Cannot create package directory");
        for (String group : new String[]{"segments", "assets"}) {
            JSONArray files = manifest.getJSONArray(group);
            for (int i = 0; i < files.length(); i++) {
                JSONObject file = files.getJSONObject(i);
                String name = file.getString("nom"), path = file.getString("url");
                if (!name.matches("(?:[EW][0-9]+_[NS][0-9]+\\.rd5|lookups\\.dat|hike2gpx\\.brf)")
                        || !path.matches("/api/paquets/[a-f0-9]{32}/" + java.util.regex.Pattern.quote(name))) {
                    throw new IllegalStateException("Invalid package file");
                }
                File target = new File(dir, name);
                if (valid(target, file)) continue;
                File part = new File(dir, name + ".part");
                downloadFile(server + path, part, file.getLong("octets"));
                if (!valid(part, file)) throw new IllegalStateException("SHA-256 mismatch: " + name);
                if (target.exists() && !target.delete()) throw new IllegalStateException("Cannot replace " + name);
                if (!part.renameTo(target)) throw new IllegalStateException("Cannot publish " + name);
            }
        }
        File temp = new File(dir, "manifest.tmp");
        try (FileOutputStream out = new FileOutputStream(temp)) {
            out.write(manifest.toString().getBytes(StandardCharsets.UTF_8));
            out.getFD().sync();
        }
        File current = new File(dir, "manifest.json");
        if (current.exists() && !current.delete()) throw new IllegalStateException("Cannot replace manifest");
        if (!temp.renameTo(current)) throw new IllegalStateException("Cannot publish manifest");
        return new Zone(dir, manifest);
    }

    private static byte[] fetch(String url) throws Exception {
        HttpsURLConnection connection = (HttpsURLConnection) new URL(url).openConnection();
        connection.setConnectTimeout(10_000);
        connection.setReadTimeout(20_000);
        try {
            if (connection.getResponseCode() != 200) throw new IllegalStateException("HTTP " + connection.getResponseCode());
            try (InputStream in = connection.getInputStream()) {
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] block = new byte[8192];
                for (int n; (n = in.read(block)) != -1;) {
                    out.write(block, 0, n);
                    if (out.size() > 32 * 1024 * 1024) throw new IllegalStateException("Manifest too large");
                }
                return out.toByteArray();
            }
        } finally { connection.disconnect(); }
    }

    private static void downloadFile(String url, File part, long expected) throws Exception {
        long offset = part.isFile() ? part.length() : 0;
        if (offset >= expected) { if (!part.delete()) throw new IllegalStateException("Invalid partial file"); offset = 0; }
        HttpsURLConnection connection = (HttpsURLConnection) new URL(url).openConnection();
        connection.setConnectTimeout(15_000);
        connection.setReadTimeout(120_000);
        if (offset > 0) connection.setRequestProperty("Range", "bytes=" + offset + "-");
        try {
            int status = connection.getResponseCode();
            if (status != (offset > 0 ? 206 : 200)) throw new IllegalStateException("HTTP " + status);
            try (InputStream in = connection.getInputStream(); FileOutputStream out = new FileOutputStream(part, offset > 0)) {
                byte[] buffer = new byte[1024 * 1024];
                for (int count; (count = in.read(buffer)) != -1;) out.write(buffer, 0, count);
                out.getFD().sync();
            }
        } finally { connection.disconnect(); }
        if (part.length() != expected) throw new IllegalStateException("Incomplete download");
    }

    private static boolean filesValid(File dir, JSONObject manifest) throws Exception {
        for (String group : new String[]{"segments", "assets"}) {
            JSONArray files = manifest.getJSONArray(group);
            for (int i = 0; i < files.length(); i++) {
                JSONObject file = files.getJSONObject(i);
                if (!valid(new File(dir, file.getString("nom")), file)) return false;
            }
        }
        return true;
    }

    private static boolean valid(File path, JSONObject description) throws Exception {
        if (!path.isFile() || path.length() != description.getLong("octets")) return false;
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileInputStream in = new FileInputStream(path)) {
            byte[] buffer = new byte[1024 * 1024];
            for (int count; (count = in.read(buffer)) != -1;) digest.update(buffer, 0, count);
        }
        return hex(digest.digest()).equalsIgnoreCase(description.getString("sha256"));
    }

    private static byte[] readAll(File file) throws Exception {
        try (FileInputStream in = new FileInputStream(file); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] block = new byte[8192];
            for (int n; (n = in.read(block)) != -1;) out.write(block, 0, n);
            return out.toByteArray();
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder text = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) text.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return text.toString();
    }
}
