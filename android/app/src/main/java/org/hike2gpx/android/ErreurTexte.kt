package org.hike2gpx.android

import android.content.Context

/**
 * Une erreur qui se dit dans la langue du téléphone : elle porte la ressource
 * de son texte (R.string, en anglais dans values, en français dans values-fr)
 * et ses arguments, et l'écran la traduit (texte). Le code métier reste ainsi
 * testable sur la JVM, sans Context, et chaque phrase n'existe qu'une fois par
 * langue, dans ses ressources.
 */
open class ErreurTexte(val texte: Int, val args: List<Any> = emptyList(), cause: Throwable? = null) :
    Exception("R.string #$texte $args", cause)

/** Le message d'une erreur dans la langue du téléphone. */
fun Context.texte(e: Throwable): String =
    if (e is ErreurTexte) getString(e.texte, *e.args.toTypedArray()) else e.message ?: e.toString()
