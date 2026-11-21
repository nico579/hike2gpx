package org.hike2gpx.android

import androidx.core.content.FileProvider

/**
 * Le FileProvider des traces : il ne partage que le dossier `traces/`, pour
 * qu'une application de cloud, de courriel ou de messagerie puisse lire le
 * GPX proposé à la fin d'un enregistrement.
 */
class FournisseurTraces : FileProvider()
