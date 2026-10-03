plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.shokiku.askalong"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.shokiku.askalong"
        minSdk = 25 // Fire OS 6 以上(Fire OS 8 は API 30 が元)
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        // クラウド(cloud/deploy.sh が作る Lambda の関数 URL)。作品の一覧と質問を返す
        buildConfigField("String", "API_URL", "\"https://nadyfdaartcc5kspwxv65ek66e0fovmj.lambda-url.us-east-1.on.aws/\"")
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    val media3 = "1.5.1"
    implementation("androidx.media3:media3-exoplayer:$media3")
    implementation("androidx.media3:media3-ui:$media3")
    implementation("androidx.media3:media3-session:$media3")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.7.0")
}
