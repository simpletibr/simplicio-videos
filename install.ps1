# install.ps1: invólucro fino (UNVERIFIED: não rodou num Windows de verdade). O ambiente do checkout é scripts\dev_install.ps1, o
# mesmo papel do scripts/dev_install.sh no Linux e no macOS. Mesmas opções: .\install.ps1 -DryRun | -With local-tts | -Python 3.12.
# Para copiar a skill para o agente use `simplicio-video install`.
$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "scripts\dev_install.ps1") @args
exit $LASTEXITCODE
