package org.hike2gpx.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.os.Looper

/**
 * L'enregistrement d'une trace, écran éteint ou application fermée : un
 * service de premier plan de type « location », comme ceux de Locus Map ou
 * d'OsmAnd. Sans lui, Android ne donne plus que quelques positions par heure
 * à une application en arrière-plan (Android 8), puis aucune (Android 10).
 *
 * Le service tient sa propre écoute GPS et verse chaque position dans
 * [EnregistrementGps], qui filtre, journalise et prévient l'écran. Sa
 * notification reste affichée tant que la trace court ; la toucher rouvre
 * l'application.
 */
class ServiceTrace : Service() {
    private var ecoute: LocationListener? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Android redémarre un service tué sans intent : la trace en mémoire
        // est alors perdue, et son journal sera récupéré par l'écran.
        if (!EnregistrementGps.actif) {
            stopSelf()
            return START_NOT_STICKY
        }
        val notification = notification()
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
            } else {
                startForeground(NOTIFICATION, notification)
            }
        } catch (e: Exception) {
            // Permission de position retirée, ou départ refusé en arrière-plan.
            stopSelf()
            return START_NOT_STICKY
        }
        // Chaque demande reprend l'écoute au rythme du filtre en vigueur : un
        // réglage de trace changé en route relance le service (MainActivity).
        arreterPosition()
        demarrerPosition()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        arreterPosition()
        super.onDestroy()
    }

    /**
     * Le GPS seul, au rythme du filtre de la trace plutôt que chaque seconde :
     * écran éteint, chaque position reçue réveille le processeur, et le filtre
     * (Locus : 10 s, 10 m) en rejetait neuf sur dix. Le réseau (Wi-Fi,
     * antennes) n'est plus demandé : en randonnée, ses positions sont trop
     * imprécises pour une trace et coûtent des balayages radio.
     */
    private fun demarrerPosition() {
        if (ecoute != null) return
        val gestionnaire = getSystemService(LOCATION_SERVICE) as LocationManager
        val nouvelle = object : LocationListener {
            override fun onLocationChanged(location: Location) = surPosition(location)
            override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
            override fun onProviderEnabled(provider: String) {}
            override fun onProviderDisabled(provider: String) {}
        }
        try {
            gestionnaire.requestLocationUpdates(LocationManager.GPS_PROVIDER, intervalleGps(EnregistrementGps.trace?.dureeMin),
                0f, nouvelle, Looper.getMainLooper())
            ecoute = nouvelle
        } catch (e: Exception) {
            // GPS absent ou permission retirée : rien à enregistrer
        }
    }

    private fun arreterPosition() {
        val active = ecoute ?: return
        try {
            (getSystemService(LOCATION_SERVICE) as LocationManager).removeUpdates(active)
        } catch (e: Exception) {
            // permission retirée entre-temps
        }
        ecoute = null
    }

    /** Une position reçue : un dernier point connu peut dater de la veille. */
    private fun surPosition(location: Location) {
        if (System.currentTimeMillis() - location.time > 120_000) return
        EnregistrementGps.ajouter(location.latitude, location.longitude,
            if (location.hasAltitude()) location.altitude else null, location.time,
            if (location.hasAccuracy()) location.accuracy.toDouble() else null)
    }

    private fun notification(): Notification {
        val gestionnaire = getSystemService(NotificationManager::class.java)
        gestionnaire.createNotificationChannel(NotificationChannel(CANAL,
            getString(R.string.trace_canal), NotificationManager.IMPORTANCE_LOW))
        val ouvrir = PendingIntent.getActivity(this, 0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        return Notification.Builder(this, CANAL)
            .setSmallIcon(R.drawable.ic_enregistrer)
            .setContentTitle(getString(R.string.trace_notification_titre))
            .setContentText(getString(R.string.trace_notification_texte))
            .setContentIntent(ouvrir)
            .setOngoing(true)
            .setShowWhen(true)
            .setUsesChronometer(true)
            .build()
    }

    companion object {
        private const val CANAL = "trace"
        private const val NOTIFICATION = 1

        fun demarrer(contexte: Context) {
            contexte.startForegroundService(Intent(contexte, ServiceTrace::class.java))
        }

        fun arreter(contexte: Context) {
            contexte.stopService(Intent(contexte, ServiceTrace::class.java))
        }
    }
}
