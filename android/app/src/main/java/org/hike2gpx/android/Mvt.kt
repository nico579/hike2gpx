package org.hike2gpx.android

/**
 * Le peu de protobuf qu'il faut pour lire une tuile vectorielle MVT
 * (spécification 2.1, telle que l'écrit mapbox-vector-tile côté PC) :
 * une tuile, ses couches, les objets et leurs attributs.
 *
 * Les géométries restent en unités de tuile ; Calques les ramène en
 * longitude / latitude avec les bornes de la tuile.
 */
object Mvt {
    const val POINT = 1
    const val LIGNE = 2
    const val POLYGONE = 3

    /** Un objet d'une couche : son type, ses lignes (ou son point) et ses attributs. */
    data class Objet(val type: Int, val lignes: List<List<DoubleArray>>, val attributs: Map<String, Any>)

    /** Les couches d'une tuile, par nom. */
    fun decoder(octets: ByteArray): Map<String, List<Objet>> {
        val tuile = Lecteur(octets)
        val couches = linkedMapOf<String, List<Objet>>()
        while (tuile.reste()) {
            val tag = tuile.tag()
            if (tag.champ == 3 && tag.fil == 2) {
                val (nom, objets) = couche(tuile.sous())
                couches[nom] = objets
            } else {
                tuile.sauter(tag.fil)
            }
        }
        return couches
    }

    private fun couche(l: Lecteur): Pair<String, List<Objet>> {
        var nom = ""
        var etendue = 4096
        val cles = mutableListOf<String>()
        val valeurs = mutableListOf<Any>()
        val brutes = mutableListOf<ByteArray>()
        while (l.reste()) {
            val tag = l.tag()
            when {
                tag.champ == 1 && tag.fil == 2 -> nom = l.chaine()
                tag.champ == 2 && tag.fil == 2 -> brutes.add(l.octets())
                tag.champ == 3 && tag.fil == 2 -> cles.add(l.chaine())
                tag.champ == 4 && tag.fil == 2 -> valeurs.add(valeur(l.sous()))
                tag.champ == 5 && tag.fil == 0 -> etendue = l.varint().toInt()
                else -> l.sauter(tag.fil)
            }
        }
        val objets = brutes.mapNotNull { objet(Lecteur(it), cles, valeurs, etendue) }
        return nom to objets
    }

    private fun valeur(l: Lecteur): Any = when (val tag = l.tag()) {
        Tag(1, 2) -> l.chaine()
        Tag(2, 5) -> Float.fromBits(l.fixe32())
        Tag(3, 1) -> Double.fromBits(l.fixe64())
        Tag(4, 0) -> l.varint()
        Tag(5, 0) -> l.varint()
        Tag(6, 0) -> zigzag(l.varint())
        Tag(7, 0) -> l.varint() != 0L
        else -> { l.sauter(tag.fil); "" }
    }

    private fun objet(l: Lecteur, cles: List<String>, valeurs: List<Any>, etendue: Int): Objet? {
        var type = 0
        val balises = mutableListOf<Int>()
        val commandes = mutableListOf<Int>()
        while (l.reste()) {
            val tag = l.tag()
            when {
                tag.champ == 2 && tag.fil == 2 -> l.paquets().forEach { balises.add(it.toInt()) }
                tag.champ == 3 && tag.fil == 0 -> type = l.varint().toInt()
                tag.champ == 4 && tag.fil == 2 -> l.paquets().forEach { commandes.add(it.toInt()) }
                else -> l.sauter(tag.fil)
            }
        }
        if (type == 0) return null
        val attributs = linkedMapOf<String, Any>()
        for (i in balises.indices step 2) {
            val cle = cles.getOrNull(balises[i]) ?: continue
            val valeur = valeurs.getOrNull(balises.getOrNull(i + 1) ?: continue) ?: continue
            attributs[cle] = valeur
        }
        return Objet(type, geometrie(type, commandes, etendue), attributs)
    }

    /**
     * Les commandes MVT (MoveTo 1, LineTo 2, ClosePath 7) en lignes de points,
     * coordonnées entières de la tuile. Un MoveTo ouvre une ligne ; pour un
     * point, chaque MoveTo est un objet distinct.
     */
    fun geometrie(type: Int, commandes: List<Int>, etendue: Int = 4096): List<List<DoubleArray>> {
        val lignes = mutableListOf<MutableList<DoubleArray>>()
        var courante: MutableList<DoubleArray>? = null
        var x = 0L
        var y = 0L
        var i = 0
        while (i < commandes.size) {
            val commande = commandes[i++]
            val id = commande and 7
            val compte = commande ushr 3
            when (id) {
                1 -> repeat(compte) {
                    if (i + 1 >= commandes.size) return lignes
                    x += zigzag(commandes[i++].toLong())
                    y += zigzag(commandes[i++].toLong())
                    if (type == POINT) {
                        lignes.add(mutableListOf(doubleArrayOf(x.toDouble(), y.toDouble())))
                        courante = null
                    } else {
                        courante = mutableListOf(doubleArrayOf(x.toDouble(), y.toDouble()))
                        lignes.add(courante!!)
                    }
                }
                2 -> {
                    if (courante == null) {
                        courante = mutableListOf()
                        lignes.add(courante!!)
                    }
                    repeat(compte) {
                        if (i + 1 >= commandes.size) return lignes
                        x += zigzag(commandes[i++].toLong())
                        y += zigzag(commandes[i++].toLong())
                        courante!!.add(doubleArrayOf(x.toDouble(), y.toDouble()))
                    }
                }
                7 -> courante = null
            }
        }
        return lignes
    }

    private fun zigzag(n: Long): Long = (n ushr 1) xor -(n and 1L)

    private data class Tag(val champ: Int, val fil: Int)

    /** Un lecteur de protobuf sur une tranche d'octets. */
    private class Lecteur(private val octets: ByteArray, private var position: Int = 0,
                          private val fin: Int = octets.size) {
        fun reste() = position < fin

        fun tag(): Tag {
            val tag = varint()
            return Tag((tag ushr 3).toInt(), (tag and 7).toInt())
        }

        fun varint(): Long {
            var resultat = 0L
            var decalage = 0
            while (decalage < 64) {
                require(position < fin) { "varint tronqué" }
                val octet = octets[position++].toInt() and 0xff
                resultat = resultat or ((octet and 0x7f).toLong() shl decalage)
                if (octet and 0x80 == 0) return resultat
                decalage += 7
            }
            throw IllegalArgumentException("varint trop long")
        }

        fun sous(): Lecteur {
            val longueur = varint().toInt()
            require(longueur >= 0 && position + longueur <= fin) { "message tronqué" }
            val l = Lecteur(octets, position, position + longueur)
            position += longueur
            return l
        }

        fun octets(): ByteArray {
            val l = sous()
            return octets.copyOfRange(l.position, l.fin)
        }

        fun chaine(): String = String(octets(), Charsets.UTF_8)

        fun fixe32(): Int {
            require(position + 4 <= fin) { "entier tronqué" }
            val v = (octets[position].toInt() and 0xff) or
                ((octets[position + 1].toInt() and 0xff) shl 8) or
                ((octets[position + 2].toInt() and 0xff) shl 16) or
                ((octets[position + 3].toInt() and 0xff) shl 24)
            position += 4
            return v
        }

        fun fixe64(): Long {
            require(position + 8 <= fin) { "entier tronqué" }
            var v = 0L
            for (i in 0 until 8) v = v or ((octets[position + i].toLong() and 0xff) shl (8 * i))
            position += 8
            return v
        }

        /** Un champ répété empaqueté (tags ou géométrie). */
        fun paquets(): List<Long> {
            val l = sous()
            val valeurs = mutableListOf<Long>()
            while (l.reste()) valeurs.add(l.varint())
            return valeurs
        }

        fun sauter(fil: Int) {
            when (fil) {
                0 -> varint()
                1 -> position += 8
                2 -> position += varint().toInt()
                5 -> position += 4
                else -> throw IllegalArgumentException("fil protobuf inconnu : $fil")
            }
            require(position <= fin) { "message tronqué" }
        }
    }
}
