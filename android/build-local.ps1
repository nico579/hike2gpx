# Construction sous Windows avec le JDK et le SDK d'Android Studio : tests
# unitaires (JVM) puis APK de débogage, comme .github/workflows/android.yml.
$ErrorActionPreference = 'Stop'
if (-not $env:JAVA_HOME -and (Test-Path (Join-Path $env:ProgramFiles 'Android\Android Studio\jbr'))) {
    $env:JAVA_HOME = Join-Path $env:ProgramFiles 'Android\Android Studio\jbr'
}
if (-not $env:ANDROID_HOME) {
    $env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
}
& (Join-Path $PSScriptRoot 'gradlew.bat') -p $PSScriptRoot :app:testDebugUnitTest :app:assembleDebug
exit $LASTEXITCODE
