plugins {
  id("com.android.application")
  id("org.jetbrains.kotlin.android")
  id("org.jetbrains.kotlin.plugin.compose")
}
android {
  namespace = "ir.vahdat.app"
  compileSdk = 35
  defaultConfig {
    applicationId = "ir.vahdat.app"
    minSdk = 26
    targetSdk = 35
    versionCode = 1
    versionName = "0.1.0-demo"
  }
  compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
  }
  kotlinOptions { jvmTarget = "17" }
  buildFeatures { compose = true }
}
dependencies {
  implementation(platform("androidx.compose:compose-bom:2024.12.01"))
  implementation("androidx.core:core-ktx:1.15.0")
  implementation("androidx.activity:activity-compose:1.9.3")
  implementation("androidx.compose.ui:ui")
  implementation("androidx.compose.foundation:foundation")
  implementation("androidx.compose.material3:material3")
  implementation("androidx.compose.material:material-icons-extended")
  implementation("com.journeyapps:zxing-android-embedded:4.3.0")
}
