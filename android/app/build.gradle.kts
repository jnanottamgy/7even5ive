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
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
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
    // Frosted glass: real backdrop blur on Android 12+, a translucent tint before. 1.6.10 is the
    // release built on Compose 1.8 and activity 1.10.1, the versions above.
    implementation("dev.chrisbanes.haze:haze:1.6.10")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}
