package org.hike2gpx.android

/**
 * Le détail d'un GPX, quel qu'il soit — itinéraire planifié, trace importée,
 * trace GPS enregistrée : sa distance, son dénivelé et sa durée.
 *
 * Le dénivelé est celui de gpx2elev, avec la première source de relief qui
 * couvre le parcours (IGN LiDAR HD, puis Mapterhorn) ; à défaut, les altitudes
 * du fichier sont lissées et cumulées de la même façon, pour un GPX relu hors
 * ligne. La durée est celle des horodatages quand ils existent (une trace
 * enregistrée), sinon celle de marche du modèle de Tobler.
 */
data class DetailTrace(
    val points: Int,
    val distanceM: Double,
    val monteeM: Int? = null,
    val descenteM: Int? = null,
    val altitudeMinM: Int? = null,
    val altitudeMaxM: Int? = null,
    val dureeS: Long? = null,
    /** Vrai quand [dureeS] vient des heures des points, faux pour Tobler. */
    val dureeReelle: Boolean = false,
    val modele: String? = null,
) {
    /** Le dénivelé a-t-il pu être calculé ? */
    val denivele: Boolean get() = monteeM != null && descenteM != null

    companion object {
        /**
         * Le détail des points d'un GPX. [sources] se lisent dans l'ordre du
         * relief (IGN puis Mapterhorn) ; [nomAltitudes] dit d'où viennent les
         * altitudes quand elles sont celles du fichier.
         */
        fun calculer(points: List<PointTrace>, sources: List<SourceRelief>,
                     nomAltitudes: String): DetailTrace {
            val coordonnees = points.map { doubleArrayOf(it.lon, it.lat) }
            val distance = if (points.size >= 2) Denivele.distances(coordonnees).last() else 0.0
            val instants = points.map { it.instant }
            // Une trace enregistrée porte l'heure de chaque point : sa durée est
            // celle du parcours, pauses comprises. Un itinéraire n'en a pas.
            val reelle = points.size >= 2 && instants.all { it > 0 } &&
                instants.zipWithNext().all { (a, b) -> b >= a } && instants.last() > instants.first()
            val altimetrie = try {
                Denivele.calculer(coordonnees, sources)
            } catch (e: Exception) {
                val altitudes = points.map { it.altitude }
                if (altitudes.any { it == null }) null
                else try {
                    Denivele.calculerAltitudes(coordonnees,
                        DoubleArray(altitudes.size) { altitudes[it]!! }, nomAltitudes)
                } catch (e: Exception) {
                    null
                }
            }
            return DetailTrace(
                points = points.size,
                distanceM = distance,
                monteeM = altimetrie?.monteeM,
                descenteM = altimetrie?.descenteM,
                altitudeMinM = altimetrie?.altitudeMinM,
                altitudeMaxM = altimetrie?.altitudeMaxM,
                dureeS = if (reelle) instants.last() - instants.first() else altimetrie?.dureeMarcheS,
                dureeReelle = reelle,
                modele = altimetrie?.modele,
            )
        }

        /**
         * Le détail d'une trace importée, segment par segment : un KML en a
         * plusieurs, et le trait qui les joint n'existe pas. Sans heures ni
         * altitudes, la durée est celle de Tobler et le dénivelé vient du relief.
         */
        fun calculerSegments(segments: List<List<Pair<Double, Double>>>, sources: List<SourceRelief>,
                             nomAltitudes: String): DetailTrace {
            var points = 0
            var distance = 0.0
            var montee = 0
            var descente = 0
            var mini = Int.MAX_VALUE
            var maxi = Int.MIN_VALUE
            var duree = 0L
            var modele: String? = null
            var calcule = false
            for (segment in segments) {
                if (segment.size < 2) continue
                val detail = calculer(segment.map { PointTrace(it.first, it.second, null, 0L) },
                    sources, nomAltitudes)
                points += detail.points
                distance += detail.distanceM
                if (!detail.denivele) continue
                montee += detail.monteeM!!
                descente += detail.descenteM!!
                mini = minOf(mini, detail.altitudeMinM!!)
                maxi = maxOf(maxi, detail.altitudeMaxM!!)
                duree += detail.dureeS ?: 0L
                if (modele == null) modele = detail.modele
                calcule = true
            }
            return DetailTrace(
                points = points,
                distanceM = distance,
                monteeM = if (calcule) montee else null,
                descenteM = if (calcule) descente else null,
                altitudeMinM = if (calcule) mini else null,
                altitudeMaxM = if (calcule) maxi else null,
                dureeS = if (calcule) duree else null,
                modele = modele,
            )
        }
    }
}
