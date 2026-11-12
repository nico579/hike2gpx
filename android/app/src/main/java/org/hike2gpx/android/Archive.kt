package org.hike2gpx.android

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.File
import java.io.InputStream
import java.io.OutputStream
import java.security.MessageDigest
import java.time.Instant
import java.util.zip.Deflater
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream

/**
 * L'archive zip des cases, celle d'archive.py sur le PC : de quoi passer des
 * cartes et des zones d'un appareil à l'autre par une clé USB ou un Drive,
 * quand le partage Wi-Fi n'est pas possible.
 *
 *   catalog.json                                  le catalogue du dépôt, en tête
 *   E5_N40/manifest.json, E5_N40/E5_N40.rd5, …    une zone de routage
 *   fonds/N43E006-scan25.mbtiles                  une carte en images
 *   fonds/N43E006-osm.map                         une carte vectorielle
 *
 * Elle se lit en flux (ZipInputStream), sans être copiée d'abord : le
 * catalogue vient donc en premier, puis chaque fichier, vérifié par sa taille
 * et son SHA-256 avant d'être installé. Aucun nom venu de l'archive ne devient
 * un chemin : seuls ceux que le catalogue annonce sont lus, sous un nom sûr.
 */
object Archive {
    const val CATALOGUE = "catalog.json"
    private const val BLOC = 1 shl 20

    class Resultat(val lots: List<String>, val fonds: List<String>)

    /**
     * Écrit l'archive des lots et des fonds choisis ; suivi(faits, total) en
     * octets. Les empreintes des lots viennent de leur manifeste ; celle d'un
     * fond se calcule ici, comme le fait le partage du PC.
     */
    fun ecrire(sortie: OutputStream, lots: List<Lot>, horsLigne: HorsLigne, fonds: List<File>,
               suivi: (Long, Long) -> Unit = { _, _ -> }, continuer: () -> Boolean = { true }) {
        val fichiers = LinkedHashMap<String, File>()           // adresse dans l'archive -> fichier
        val entreesLots = JSONArray()
        for (lot in lots) {
            val dossier = File(horsLigne.racine, lot.case)
            val manifeste = File(dossier, "manifest.json")
            val json = JSONObject(manifeste.readText())
            val liste = JSONArray()
            for (f in lot.fichiers) {
                val chemin = if (f.nom == "${lot.case}.rd5") File(horsLigne.segmentsDe(lot), f.nom) else File(dossier, f.nom)
                liste.put(JSONObject().put("nom", f.nom).put("octets", f.octets).put("sha256", f.sha256)
                    .put("url", "${lot.case}/${f.nom}"))
                fichiers["${lot.case}/${f.nom}"] = chemin
            }
            liste.put(JSONObject().put("nom", "manifest.json").put("octets", manifeste.length())
                .put("sha256", empreinte(manifeste)).put("url", "${lot.case}/manifest.json"))
            fichiers["${lot.case}/manifest.json"] = manifeste
            json.put("fichiers", liste)
            json.put("octets", (0 until liste.length()).sumOf { liste.getJSONObject(it).getLong("octets") })
            entreesLots.put(json)
        }
        val images = JSONArray()
        val cartes = JSONArray()
        for (f in fonds) {
            if (!continuer()) throw Abandon()
            val nom = f.nameWithoutExtension
            (if (f.name.endsWith(".map")) cartes else images).put(JSONObject().put("nom", nom)
                .put("source", Fonds.source(nom)).put("octets", f.length()).put("sha256", empreinte(f))
                .put("url", "fonds/${f.name}"))
            fichiers["fonds/${f.name}"] = f
        }
        val catalogue = JSONObject().put("format", Catalogue.FORMAT).put("genere", Instant.now().toString())
            .put("lots", entreesLots).put("fonds", images)
        if (cartes.length() > 0) catalogue.put("cartes", cartes)

        val total = fichiers.values.sumOf { it.length() }
        var faits = 0L
        val zip = ZipOutputStream(sortie)
        // Deflate au plus rapide, comme le PC : des tuiles JPEG n'y gagnent presque rien.
        zip.setLevel(Deflater.BEST_SPEED)
        zip.putNextEntry(ZipEntry(CATALOGUE))
        zip.write(catalogue.toString(1).toByteArray(Charsets.UTF_8))
        zip.closeEntry()
        val bloc = ByteArray(BLOC)
        for ((adresse, chemin) in fichiers) {
            zip.putNextEntry(ZipEntry(adresse))
            chemin.inputStream().use { entree ->
                while (true) {
                    if (!continuer()) throw Abandon()
                    val n = entree.read(bloc)
                    if (n < 0) break
                    zip.write(bloc, 0, n)
                    faits += n
                    suivi(faits, total)
                }
            }
            zip.closeEntry()
        }
        zip.finish()
        sortie.flush()
    }

    /**
     * Installe les zones et les cartes de l'archive lue dans entree ; travail
     * est un dossier vide qu'on peut effacer. suivi(faits, total) en octets.
     */
    fun importer(entree: InputStream, horsLigne: HorsLigne, fonds: Fonds, travail: File,
                 suivi: (Long, Long) -> Unit = { _, _ -> }, continuer: () -> Boolean = { true }): Resultat {
        travail.deleteRecursively()
        travail.mkdirs()
        try {
            val zip = ZipInputStream(BufferedInputStream(entree, BLOC))
            if (zip.nextEntry?.name != CATALOGUE) throw ErreurDepot(R.string.err_archive_catalogue)
            val catalogue = Catalogue.lire(String(zip.readBytes(), Charsets.UTF_8))
            val dossierFonds = File(travail, "fonds")
            val cartes = catalogue.fonds + catalogue.cartes
            val attendus = HashMap<String, Pair<File, Fichier>>()
            for (lot in catalogue.lots)
                for (f in lot.fichiers) attendus[f.url] = File(File(travail, lot.case), f.nom) to f
            for (fond in cartes) {
                val nom = "${Catalogue.nomSur(fond.nom)}${fond.extension}"
                attendus[fond.url] = File(dossierFonds, nom) to Fichier(nom, fond.octets, fond.sha256, fond.url)
            }
            val total = attendus.values.sumOf { it.second.octets }
            if (travail.usableSpace < total + Depot.MARGE_DISQUE)
                throw ErreurDepot(R.string.err_place, listOf(total / 1_000_000 + 1))
            var faits = 0L
            val bloc = ByteArray(BLOC)
            while (true) {
                val element = zip.nextEntry ?: break
                val (cible, f) = attendus[element.name] ?: continue     // un fichier hors catalogue est ignoré
                cible.parentFile?.mkdirs()
                val h = MessageDigest.getInstance("SHA-256")
                cible.outputStream().use { sortie ->
                    while (true) {
                        if (!continuer()) throw Abandon()
                        val n = zip.read(bloc)
                        if (n < 0) break
                        sortie.write(bloc, 0, n)
                        h.update(bloc, 0, n)
                        faits += n
                        suivi(faits, total)
                    }
                }
                if (cible.length() != f.octets) throw ErreurLot(R.string.err_fichier_taille, listOf(f.nom))
                if (hexadecimal(h.digest()) != f.sha256) throw ErreurLot(R.string.err_fichier_empreinte, listOf(f.nom))
            }
            // Tout est là et juste : les zones passent par HorsLigne.installer, qui les revérifie.
            val lots = catalogue.lots.map { horsLigne.installer(File(travail, it.case)).case }
            val noms = cartes.map { fond ->
                val (fichier, f) = attendus.getValue(fond.url)
                if (!fichier.isFile) throw ErreurLot(R.string.err_fichier_taille, listOf(f.nom))
                fonds.installer(fichier, fond)
                fond.nom
            }
            return Resultat(lots, noms)
        } finally {
            travail.deleteRecursively()
        }
    }

    /** Le nom proposé pour l'archive : hike2gpx-N43E006-scan25-et-2.zip. */
    fun nomPropose(noms: List<String>): String =
        "hike2gpx-${noms.firstOrNull() ?: "cartes"}${if (noms.size > 1) "-et-${noms.size - 1}" else ""}.zip"
}
