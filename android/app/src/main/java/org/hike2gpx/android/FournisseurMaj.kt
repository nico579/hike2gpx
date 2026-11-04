package org.hike2gpx.android

import androidx.core.content.FileProvider

/** Un FileProvider propre à l'application, comme UpdateFileProvider de gpxelev : il ne partage que cache/maj. */
class FournisseurMaj : FileProvider()
