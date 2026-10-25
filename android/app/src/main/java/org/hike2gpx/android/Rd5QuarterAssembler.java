package org.hike2gpx.android;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.Set;
import java.util.zip.CRC32;

/** Rebuilds a BRouter 5° RD5 from downloaded 0.25° fragments. */
final class Rd5QuarterAssembler {
    private static final int MICRO = 32;
    private static final int SUB_INDEX = MICRO * MICRO * 4;
    private static final long POSITION_MASK = 0x0000ffffffffffffL;

    private Rd5QuarterAssembler() {}

    static String key(int degree, int x, int y) { return degree + ":" + x + ":" + y; }

    static void assemble(JSONObject manifest, File directory, File output, Set<String> selected) throws Exception {
        if (manifest.getInt("format") != 2) throw new IOException("Unsupported RD5 fragment format");
        JSONArray fragments = manifest.getJSONArray("fragments");
        if (fragments.length() != 400) throw new IOException("Incomplete RD5 fragment manifest");
        byte[] originalHeader = unhex(manifest.getString("entete"));
        byte[] originalFooter = unhex(manifest.getString("pied"));
        if (originalHeader.length != 200 || originalFooter.length < 113
                || (readInt(originalFooter, 8) != (crc(originalHeader) ^ 2)))
            throw new IOException("Invalid RD5 header or footer");
        File temporary = new File(output.getParentFile(), output.getName() + ".part");
        int[] subCrc = new int[25];
        long[] positions = new long[25];
        try (RandomAccessFile result = new RandomAccessFile(temporary, "rw")) {
            result.setLength(0);
            result.write(new byte[200]);
            for (int degree = 0; degree < 25; degree++) {
                byte[][] caches = new byte[MICRO * MICRO][];
                boolean any = false;
                for (int y = 0; y < 4; y++) {
                    for (int x = 0; x < 4; x++) {
                        JSONObject fragment = fragments.getJSONObject(degree * 16 + y * 4 + x);
                        if (fragment.getInt("case") != degree || fragment.getInt("x") != x
                                || fragment.getInt("y") != y) throw new IOException("RD5 fragment order changed");
                        if (!selected.contains(key(degree, x, y)) || fragment.isNull("nom")) continue;
                        String name = fragment.getString("nom");
                        if (!name.matches("[0-9]{2}_[0-3]_[0-3]\\.rd5q"))
                            throw new IOException("Invalid RD5 fragment name");
                        File file = new File(directory, name);
                        if (file.length() != fragment.getLong("octets") || file.length() < 256
                                || file.length() > 64L * 1024 * 1024) throw new IOException("RD5 fragment size mismatch");
                        byte[] data = Files.readAllBytes(file.toPath());
                        if (!hex(MessageDigest.getInstance("SHA-256").digest(data))
                                .equalsIgnoreCase(fragment.getString("sha256")))
                            throw new IOException("RD5 fragment checksum mismatch");
                        try (DataInputStream in = new DataInputStream(new java.io.ByteArrayInputStream(data))) {
                            int[] lengths = new int[64];
                            long total = 256;
                            for (int i = 0; i < 64; i++) {
                                lengths[i] = in.readInt();
                                if (lengths[i] < 0) throw new IOException("Invalid microcache length");
                                total += lengths[i];
                            }
                            if (total != data.length) throw new IOException("Invalid RD5 fragment contents");
                            for (int dy = 0; dy < 8; dy++) {
                                for (int dx = 0; dx < 8; dx++) {
                                    int part = dy * 8 + dx;
                                    int index = (y * 8 + dy) * MICRO + x * 8 + dx;
                                    if (lengths[part] > 0) {
                                        caches[index] = new byte[lengths[part]];
                                        in.readFully(caches[index]);
                                        any = true;
                                    }
                                }
                            }
                        }
                    }
                }
                if (any) {
                    ByteArrayOutputStream indexBytes = new ByteArrayOutputStream(SUB_INDEX);
                    try (DataOutputStream index = new DataOutputStream(indexBytes)) {
                        long end = SUB_INDEX;
                        for (byte[] cache : caches) {
                            if (cache != null) end += cache.length;
                            if (end > Integer.MAX_VALUE) throw new IOException("RD5 subfile too large");
                            index.writeInt((int) end);
                        }
                    }
                    byte[] index = indexBytes.toByteArray();
                    subCrc[degree] = crc(index);
                    result.write(index);
                    for (byte[] cache : caches) if (cache != null) result.write(cache);
                }
                positions[degree] = result.getFilePointer();
            }
            byte[] header = new byte[200];
            for (int degree = 0; degree < 25; degree++) {
                long old = readLong(originalHeader, degree * 8);
                long current = (old & ~POSITION_MASK) | positions[degree];
                putLong(header, degree * 8, current);
            }
            result.write(originalFooter, 0, 8);
            result.writeInt(crc(header) ^ 2);
            for (int value : subCrc) result.writeInt(value);
            result.write(originalFooter, 112, originalFooter.length - 112);
            result.seek(0);
            result.write(header);
            result.getFD().sync();
        }
        Files.move(temporary.toPath(), output.toPath(),
                StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
    }

    private static int crc(byte[] value) {
        CRC32 crc = new CRC32();
        crc.update(value);
        return (int) crc.getValue() ^ -1;
    }

    private static int readInt(byte[] b, int offset) {
        return ((b[offset] & 255) << 24) | ((b[offset + 1] & 255) << 16)
                | ((b[offset + 2] & 255) << 8) | (b[offset + 3] & 255);
    }

    private static long readLong(byte[] b, int offset) {
        long value = 0;
        for (int i = 0; i < 8; i++) value = value << 8 | (b[offset + i] & 255L);
        return value;
    }

    private static void putLong(byte[] b, int offset, long value) {
        for (int i = 7; i >= 0; i--) { b[offset + i] = (byte) value; value >>>= 8; }
    }

    private static byte[] unhex(String text) throws IOException {
        if ((text.length() & 1) != 0) throw new IOException("Invalid hexadecimal field");
        byte[] value = new byte[text.length() / 2];
        for (int i = 0; i < value.length; i++) {
            int n = Character.digit(text.charAt(i * 2), 16);
            int m = Character.digit(text.charAt(i * 2 + 1), 16);
            if (n < 0 || m < 0) throw new IOException("Invalid hexadecimal field");
            value[i] = (byte) (n * 16 + m);
        }
        return value;
    }

    private static String hex(byte[] bytes) {
        StringBuilder value = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) value.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return value.toString();
    }
}
