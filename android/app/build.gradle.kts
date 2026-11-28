plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

fun prop(name: String, fallback: String) = (findProperty(name) as String?) ?: fallback

android {
    namespace = "com.sevenfive.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.sevenfive.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"

        buildConfigField("String", "DEFAULT_SERVER", "\"${prop("sevenfive.defaultServer", "")}\"")
        buildConfigField("String", "DEFAULT_HOST", "\"${prop("sevenfive.defaultHost", "10.0.2.2")}\"")
        buildConfigField("String", "STUDENT_TOKEN", "\"${prop("sevenfive.studentToken", "demo-student-token")}\"")
        buildConfigField("String", "COLLEGE", "\"${prop("sevenfive.college", "mockcollege")}\"")
        // Firebase, only to wake the phone (notify/Push.kt). All four empty: no Firebase at all,
        // and the outbox is still pulled every 15 minutes. These are app settings, not secrets.
        buildConfigField("String", "FCM_APP_ID", "\"${prop("sevenfive.fcmAppId", "")}\"")
        buildConfigField("String", "FCM_API_KEY", "\"${prop("sevenfive.fcmApiKey", "")}\"")
        buildConfigField("String", "FCM_PROJECT_ID", "\"${prop("sevenfive.fcmProjectId", "")}\"")
        buildConfigField("String", "FCM_SENDER_ID", "\"${prop("sevenfive.fcmSenderId", "")}\"")
        // The portal the WebView opens, when it is not the demo server's own mock portal. Set it
        // with the matching college to point the app at a real portal (e.g. MSRIT), uploads still
        // going to sevenfive.defaultServer. Empty = use the server's mock portal.
        buildConfigField("String", "PORTAL", "\"${prop("sevenfive.portal", "")}\"")
    }

    // One committed debug key, so every CI build signs the same way and installs as an update
    // over the last one. It only signs test builds; it is not a release key and holds no secret.
    signingConfigs {
        getByName("debug") {
            storeFile = file("debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // The prototype ships debug builds only; release signs with the debug key so the
            // APK still installs if someone builds it.
            signingConfig = signingConfigs.getByName("debug")
        }
        // The build to install on a phone. Debug builds run Compose without ART's optimisations
        // and without R8, which shows as lag and dropped frames in the blur and the springs; this
        // is a release build (optimised, Compose's baseline profiles installed) that keeps the
        // debug build's network rules, so the laptop fallback still works. Same key as debug, so
        // it installs as an update over a debug build.
        create("demo") {
            initWith(getByName("release"))
            isMinifyEnabled = true
            // Drops resources nothing uses (libraries bring many); nothing looks one up by name.
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("release")
        }
    }
    sourceSets.getByName("demo").res.srcDirs("src/debug/res")

    // The app is in English: the libraries' translations into 80+ languages are never shown.
    androidResources {
        localeFilters += listOf("en")
    }

    packaging {
        resources {
            // Metadata only kotlin-reflect reads (the app doesn't use it) and the coroutines
            // debugger's probes. The libraries' licence files stay.
            excludes += listOf("kotlin/**.kotlin_builtins", "DebugProbesKt.bin")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    testOptions {
        // The UI tests (src/test/.../ui) run on the JVM under Robolectric, with the app's own
        // resources (fonts, strings, theme).
        unitTests.isIncludeAndroidResources = true
    }
}

// Robolectric fetches its Android runtime (about 200 MB) from Maven Central on first use. Where
// Maven Central refuses it (it limits downloads per address), point the tests at a copy fetched
// once, kept under its Maven file name: -Psevenfive.robolectricDeps=DIR or ROBOLECTRIC_DEPS_DIR.
val robolectricDeps = (findProperty("sevenfive.robolectricDeps") as String?) ?: System.getenv("ROBOLECTRIC_DEPS_DIR")
tasks.withType<Test>().configureEach {
    // Robolectric's Android 16 runtime reaches into the JDK's file descriptors.
    jvmArgs("--add-opens=java.base/jdk.internal.access=ALL-UNNAMED", "--add-opens=java.base/java.io=ALL-UNNAMED")
    // The UI tests save screenshots of what they drew (build/outputs/roborazzi), for review.
    systemProperty("roborazzi.test.record", "true")
    if (robolectricDeps != null) {
        systemProperty("robolectric.offline", "true")
        systemProperty("robolectric.dependency.dir", robolectricDeps)
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.06.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    debugImplementation("androidx.compose.ui:ui-tooling")

    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.1")
    implementation("androidx.navigation:navigation-compose:2.9.0")
    // WebViewCompat.addDocumentStartJavaScript, to neutralise the portal's WebView fingerprint
    // before its own scripts run.
    implementation("androidx.webkit:webkit:1.12.1")
    // The home-screen widget, written in Compose.
    implementation("androidx.glance:glance-appwidget:1.1.1")

    // Pulls the outbox every 15 minutes and keeps the portal session alive in the background.
    implementation("androidx.work:work-runtime-ktx:2.10.2")
    // Wakes the phone when the outbox has something (no content travels through it). Started by
    // hand from build settings, so no google-services.json or plugin is needed.
    implementation("com.google.firebase:firebase-messaging:24.1.2")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    // UI tests without a phone: Compose's test rule under Robolectric, which also draws the
    // screenshots (native graphics). The test manifest is debug-only: never in a release.
    testImplementation(composeBom)
    testImplementation("androidx.compose.ui:ui-test-junit4")
    testImplementation("org.robolectric:robolectric:4.17")
    testImplementation("io.github.takahirom.roborazzi:roborazzi:1.77.0")
    testImplementation("io.github.takahirom.roborazzi:roborazzi-compose:1.77.0")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
