// Kotlin est intégré à AGP depuis sa version 9 : pas de plugin Kotlin à appliquer.
plugins {
    alias(libs.plugins.android.application)
}

// Une seule version pour le programme et l'application : celle du paquet
// Python, que la release vérifie contre son tag. 0.8.0 donne le code 800 ;
// le code ne fait que croître, condition d'Android pour une mise à jour.
val versionHike2gpx: String = Regex("""__version__\s*=\s*"([^"]+)"""")
    .find(rootProject.file("../hike2gpx/__init__.py").readText())!!.groupValues[1]
val codeHike2gpx: Int = versionHike2gpx.split(".").map { it.toInt() }
    .let { (majeure, mineure, corrective) -> majeure * 10000 + mineure * 100 + corrective }

android {
    namespace = "org.hike2gpx.android"
    compileSdk = 36
    defaultConfig {
        applicationId = "org.hike2gpx.android"
        minSdk = 26
        targetSdk = 36
        versionCode = codeHike2gpx
        versionName = versionHike2gpx
    }
    // Comme gpx2elev : la release restaure la clé du projet (secret
    // ANDROID_KEYSTORE_BASE64) sous app/debug.keystore. Une clé stable, sinon
    // Android refuse d'installer la version suivante par-dessus. Sans ce
    // fichier, en local ou dans une PR, Gradle prend sa clé de débogage.
    signingConfigs.getByName("debug") {
        val clePersonnelle = file("debug.keystore")
        if (clePersonnelle.exists()) {
            storeFile = clePersonnelle
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }
    buildTypes {
        release {
            // Pas de réduction R8 : BRouter n'a pas été éprouvé ainsi.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    // BRouter 1.7.10, sous-module épinglé, compilé dans l'APK : le moteur
    // tourne dans le processus de l'application, sans serveur.
    sourceSets.getByName("main") {
        java.directories.addAll(listOf(
            "../brouter/brouter-util/src/main/java",
            "../brouter/brouter-codec/src/main/java",
            "../brouter/brouter-expressions/src/main/java",
            "../brouter/brouter-mapaccess/src/main/java",
            "../brouter/brouter-core/src/main/java",
        ))
    }
}

dependencies {
    implementation(libs.osmdroid)
    implementation(libs.gson)
    testImplementation(libs.junit)
    // org.json d'Android n'existe pas sur la JVM des tests : la bibliothèque d'origine.
    testImplementation(libs.json)
}
