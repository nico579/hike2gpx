package org.hike2gpx.android

import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.Locale
import kotlin.math.abs

/** Une ville trouvée : son nom, son détail (département, région, pays) et son centre. */
data class Ville(val nom: String, val detail: String, val lat: Double, val lon: Double)

class ErreurRecherche(message: String) : Exception(message)

/**
 * La recherche de ville de la page : les communes françaises d'abord
 * (geo.api.gouv.fr), puis le reste du monde par Nominatim, le moteur
 * d'OpenStreetMap. Une seule requête, et seulement quand la France n'a rien
 * donné, comme le demandent les conditions d'usage de Nominatim.
 *
 * Les fonctions de lecture prennent le texte de la réponse en paramètre :
 * l'analyse se teste sans réseau, la requête se remplace.
 */
object Communes {
    const val API_COMMUNES = "https://geo.api.gouv.fr/communes"
    const val API_NOMINATIM = "https://nominatim.openstreetmap.org/search"
    const val AGENT = "hike2gpx-android/0.2 (+https://github.com/nico579/hike2gpx)"
    const val LIMITE = 8
    const val MAX_OCTETS = 65_536

    /**
     * Les villes qui répondent au nom cherché, la correspondance exacte
     * d'abord. Le service français en panne ne bloque pas : Nominatim prend
     * le relais. Sans aucune réponse, la liste est vide.
     */
    fun chercher(nom: String, lire: (String) -> String = ::lireUrl): List<Ville> {
        val requete = nom.trim()
        if (requete.length < 2 || requete.length > 80)
            throw ErreurRecherche("Saisissez au moins deux caractères pour rechercher une ville.")
        val villes = try {
            communesFrancaises(lire(urlCommunes(requete)))
        } catch (e: Exception) {
            emptyList()         // le service français en panne : le reste du monde la couvre aussi
        }
        if (villes.isNotEmpty()) return trier(villes, requete)
        val monde = try {
            lieuxDuMonde(lire(urlNominatim(requete)))
        } catch (e: Exception) {
            throw ErreurRecherche(e.message ?: e.toString())
        }
        return trier(monde, requete)
    }

    /**
     * Les coordonnées « lat, lon » de la page : virgule, point-virgule ou
     * espace, point ou virgule décimale (le point-virgule lève l'ambiguïté).
     */
    fun lireCoordonnees(recherche: String): Pair<Double, Double>? {
        val point = Regex("""^\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*$""")
            .find(recherche)
        val parties = when {
            point != null -> listOf(point.groupValues[1], point.groupValues[2])
            recherche.contains(";") -> recherche.split(";")
            else -> recherche.trim().split(Regex("""\s+"""))
        }
        if (parties.size != 2) return null
        val nombre = Regex("""^[+-]?\d+(?:[.,]\d+)?$""")
        if (!parties.all { nombre.matches(it.trim()) }) return null
        val nombres = parties.map { it.trim().replace(',', '.').toDoubleOrNull() ?: return null }
        val lat = nombres[0]
        val lon = nombres[1]
        if (!lat.isFinite() || !lon.isFinite()) return null
        return if (abs(lat) <= 90 && abs(lon) <= 180) lat to lon else null
    }

    /** Les communes françaises : nom, département, centre. */
    fun communesFrancaises(texte: String): List<Ville> {
        val reponse = JSONArray(texte)
        val villes = mutableListOf<Ville>()
        for (i in 0 until reponse.length()) {
            val commune = reponse.optJSONObject(i) ?: continue
            val centre = commune.optJSONObject("centre") ?: continue
            val coords = centre.optJSONArray("coordinates") ?: continue
            if (coords.length() != 2) continue
            val point = point(coords.optDouble(1, Double.NaN), coords.optDouble(0, Double.NaN)) ?: continue
            val nom = texte(commune, "nom")
            if (nom.isEmpty()) continue
            villes.add(Ville(nom, texte(commune.optJSONObject("departement"), "nom"),
                point.first, point.second))
        }
        return villes
    }

    /** Les villes et villages du monde : nom, région et pays. */
    fun lieuxDuMonde(texte: String): List<Ville> {
        val reponse = JSONArray(texte)
        val villes = mutableListOf<Ville>()
        for (i in 0 until reponse.length()) {
            val lieu = reponse.optJSONObject(i) ?: continue
            val point = point(lieu.optDouble("lat", Double.NaN), lieu.optDouble("lon", Double.NaN))
                ?: continue
            val nom = texte(lieu, "name")
            if (nom.isEmpty()) continue
            val adresse = lieu.optJSONObject("address")
            val region = listOf("state", "region", "county").firstNotNullOfOrNull {
                texte(adresse, it).takeIf { valeur -> valeur.isNotEmpty() }
            }
            val pays = texte(adresse, "country").takeIf { it.isNotEmpty() }
            villes.add(Ville(nom, listOfNotNull(region, pays).joinToString(", "),
                point.first, point.second))
        }
        return villes
    }

    private fun trier(villes: List<Ville>, nom: String): List<Ville> =
        villes.sortedBy { it.nom.lowercase(Locale.ROOT) != nom.lowercase(Locale.ROOT) }

    private fun point(lat: Double, lon: Double): Pair<Double, Double>? =
        if (lat.isFinite() && lon.isFinite() && lat in -90.0..90.0 && lon in -180.0..180.0)
            lat to lon else null

    private fun texte(objet: JSONObject?, cle: String): String {
        if (objet == null || !objet.has(cle) || objet.isNull(cle)) return ""
        return objet.optString(cle)
    }

    private fun urlCommunes(nom: String) = API_COMMUNES + "?" + parametres(listOf(
        "nom" to nom, "fields" to "nom,code,centre,departement",
        "boost" to "population", "limit" to LIMITE.toString()))

    private fun urlNominatim(nom: String) = API_NOMINATIM + "?" + parametres(listOf(
        "q" to nom, "format" to "jsonv2", "addressdetails" to "1",
        "limit" to LIMITE.toString(), "featureType" to "settlement",
        "accept-language" to "fr,en"))

    private fun parametres(valeurs: List<Pair<String, String>>) = valeurs.joinToString("&") {
        (cle, valeur) -> cle + "=" + URLEncoder.encode(valeur, "UTF-8")
    }

    /** Une réponse JSON de 64 Ko au plus, lue comme la page (8 s au plus). */
    private fun lireUrl(adresse: String): String {
        val connexion = URL(adresse).openConnection() as HttpURLConnection
        connexion.connectTimeout = 8_000
        connexion.readTimeout = 8_000
        connexion.setRequestProperty("User-Agent", AGENT)
        connexion.setRequestProperty("Accept", "application/json")
        try {
            val code = connexion.responseCode
            if (code != HttpURLConnection.HTTP_OK) throw IOException("réponse HTTP $code")
            val bloc = ByteArray(8_192)
            val sortie = ByteArrayOutputStream()
            connexion.inputStream.use { entree ->
                while (true) {
                    val n = entree.read(bloc)
                    if (n < 0) break
                    sortie.write(bloc, 0, n)
                    if (sortie.size() > MAX_OCTETS) throw ErreurRecherche("réponse trop volumineuse")
                }
            }
            return sortie.toString("UTF-8")
        } finally {
            connexion.disconnect()
        }
    }
}
