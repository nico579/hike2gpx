// Kotlin est intégré à AGP depuis sa version 9 : pas de plugin Kotlin à appliquer.
plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "org.hike2gpx.android"
    compileSdk = 36
    defaultConfig {
        applicationId = "org.hike2gpx.android"
        minSdk = 26
        targetSdk = 36
        versionCode = 2
        versionName = "0.2.0"
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
