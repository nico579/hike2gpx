$ErrorActionPreference = 'Stop'
if (-not $env:JAVA_HOME -and (Test-Path (Join-Path $env:ProgramFiles 'Android\Android Studio\jbr'))) {
    $env:JAVA_HOME = Join-Path $env:ProgramFiles 'Android\Android Studio\jbr'
}
if (-not $env:ANDROID_HOME) {
    $env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
}
& (Join-Path $PSScriptRoot 'gradlew.bat') -p $PSScriptRoot :app:assembleDebug
exit $LASTEXITCODE
