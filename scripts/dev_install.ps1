<#
.SYNOPSIS
  Ambiente de desenvolvimento do simplicio-video no checkout (Windows): o equivalente de scripts/dev_install.sh.

.DESCRIPTION
  UNVERIFIED: ninguém rodou este script num Windows de verdade ainda (o repositório foi escrito no Linux, sem PowerShell). Ele segue
  linha por linha o scripts/dev_install.sh, que roda com fakes nos testes. Rode com -DryRun primeiro e cole o resultado na issue.

  É o que o `simplicio-video install` fazia antes do ADR-0020. Agora o `simplicio-video install` copia a skill para o host do agente
  (como o `install` do simplicio-loop) e o ambiente do checkout mora aqui, como o loop tem o seu scripts/dev_install.sh.

  Faz, nesta ordem: checa Node 22 ou superior, ffmpeg com libass e 5 GB livres (sem instalar nada no sistema); garante o uv (se faltar,
  oferece instalar com o script oficial e só baixa com a sua confirmação); cria o .venv com o Python pedido e instala o pacote editável
  com os extras (uv pip install -e); constrói web/ se ele existir; roda `simplicio-video doctor` e imprime os próximos passos. Não pede
  administrador, não usa o python do sistema (o uv traz o Python) e rodar de novo não muda nada que já está certo. Um .venv com outro
  Python é um conflito: o script diz o que apagar e não troca sozinho.

.PARAMETER With
  Extras do pacote separados por vírgula, ex.: local-tts,mcp. No PowerShell `-With local-tts,mcp` chega como uma lista: o script junta
  os itens com vírgula.

  O Windows de cliente vem com a política de execução Restricted: `powershell -File x.ps1` pararia com "running scripts is disabled".
  O `-ExecutionPolicy Bypass` dos exemplos vale só para esse processo e não muda a política da máquina (UNVERIFIED: sem Windows real).

.PARAMETER Python
  Python do .venv (padrão: 3.12; os extras do CrewAI exigem menos de 3.14).

.PARAMETER DryRun
  Lista o plano e sai; não cria nem altera nada.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1 -DryRun

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1 -With local-tts -Python 3.12
#>
[CmdletBinding()]
param(
    [string[]]$With = @(),
    [string]$Python = "3.12",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# `-With local-tts,mcp` typed in PowerShell is an array: join it, or the check below would refuse it as "invalid extras"
$WithTexto = (($With | Where-Object { $_ -ne "" }) -join ",")

$MinNode = 22
$MinDiskGb = 5
$Raiz = Split-Path -Parent $PSScriptRoot
$VenvPy = ".venv\Scripts\python.exe"
$Sv = ".venv\Scripts\simplicio-video.exe"

function Fail([string]$Message) {
    [Console]::Error.WriteLine("dev_install.ps1: $Message")
    exit 1
}

function Get-NodeMajor {
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    if (-not $cmd) { return 0 }
    try {
        $text = (& node --version 2>$null | Select-Object -First 1)
        return [int](([string]$text).TrimStart("v").Split(".")[0])
    } catch {
        return 0
    }
}

function Test-FfmpegLibass {
    $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if (-not $cmd) { return $false }
    try {
        $text = (& ffmpeg -hide_banner -version 2>$null) -join "`n"
        return ($text -match "--enable-libass")
    } catch {
        return $false
    }
}

function Get-FreeGb {
    # 9999 = could not measure (a network path, say): the check is skipped, as the shell script skips what it cannot read
    try {
        $info = New-Object System.IO.DriveInfo ([System.IO.Path]::GetPathRoot($Raiz))
        return [int][math]::Floor($info.AvailableFreeSpace / 1GB)
    } catch {
        return 9999
    }
}

# O uv no PATH e, se não estiver, onde o instalador dele costuma deixá-lo (~\.local\bin e ~\.cargo\bin).
function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($candidate in @("$HOME\.local\bin\uv.exe", "$HOME\.cargo\bin\uv.exe")) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

function Get-VenvVersion {
    $cfg = Join-Path $Raiz ".venv\pyvenv.cfg"
    if (-not (Test-Path -LiteralPath $cfg)) { return "" }
    foreach ($line in Get-Content -LiteralPath $cfg) {
        if ($line -match "^version(_info)?\s*=\s*(\d+\.\d+)") { return $Matches[2] }
    }
    return ""
}

function Get-PackageTarget {
    if ($WithTexto -ne "") { return ".[" + $WithTexto + "]" }
    return "."
}

if ($Python -notmatch '^3\.\d+$') { Fail "versão de Python inválida: $Python (use algo como 3.12)" }
if ($WithTexto -ne "" -and $WithTexto -notmatch '^[a-z][a-z0-9-]*(,[a-z][a-z0-9-]*)*$') {
    Fail "extras inválidos: $WithTexto (use nomes separados por vírgula, ex.: local-tts,mcp)"
}

if ($DryRun) {
    $subExtras = "sem extras"
    if ($WithTexto -ne "") { $subExtras = "extras: $WithTexto" }
    $statusNode = "falta: precisa de Node $MinNode ou superior"
    if ((Get-NodeMajor) -ge $MinNode) { $statusNode = "ok" }
    $statusFfmpeg = "falta: ffmpeg com libass"
    if (Test-FfmpegLibass) { $statusFfmpeg = "ok" }
    $statusUv = "ausente: ofereceria instalar com a sua confirmação"
    if (Find-Uv) { $statusUv = "ok" }
    Write-Output "dev_install.ps1 -DryRun: nada será criado nem alterado. Plano:"
    Write-Output "  1. checar Node $MinNode ou superior ........ $statusNode"
    Write-Output "  2. checar ffmpeg com libass .......... $statusFfmpeg"
    Write-Output "  3. checar $MinDiskGb GB livres (em $Raiz) ..... hoje: $(Get-FreeGb) GB"
    Write-Output "  4. garantir o uv ...................... $statusUv"
    Write-Output "  5. criar .venv com Python $Python e instalar o pacote ($subExtras):"
    Write-Output "       uv venv --python $Python .venv"
    Write-Output "       uv pip install --python $VenvPy -e `"$(Get-PackageTarget)`""
    if (Test-Path -LiteralPath (Join-Path $Raiz "web\package.json")) {
        Write-Output "  6. construir web/ (npm --prefix web ci && npm --prefix web run build)"
    } else {
        Write-Output '  6. web/ ainda não existe: registrar "web/ chega com a #34" e seguir'
    }
    Write-Output "  7. rodar $Sv doctor"
    Write-Output "  8. imprimir os próximos passos (install, setup e doctor)"
    exit 0
}

Set-Location -LiteralPath $Raiz

if ((Get-NodeMajor) -lt $MinNode) {
    Fail "Node $MinNode ou superior é necessário. Baixe em https://nodejs.org (ou use o nvm-windows) e rode de novo."
}
if (-not (Test-FfmpegLibass)) {
    Fail "ffmpeg com libass é necessário. Windows: 'winget install Gyan.FFmpeg'. Rode de novo depois."
}
if ((Get-FreeGb) -lt $MinDiskGb) {
    Fail "são necessários $MinDiskGb GB livres em $Raiz (hoje: $(Get-FreeGb) GB)."
}

$Uv = Find-Uv
if (-not $Uv) {
    if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) {
        Fail "uv não encontrado. Instale em https://docs.astral.sh/uv/ e rode de novo (ou rode num terminal para instalar daqui)."
    }
    $resp = Read-Host "uv não encontrado. Instalar agora com o script oficial (https://astral.sh/uv/install.ps1)? [s/N]"
    if ($resp -notmatch '^(s|sim|y|yes)$') { Fail "uv é necessário. Instale e rode de novo." }
    & powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$HOME\.local\bin;$env:Path"
    $Uv = Find-Uv
    if (-not $Uv) { Fail "o uv não apareceu no PATH depois da instalação." }
}

if (Test-Path -LiteralPath ".venv") {
    $atual = Get-VenvVersion
    if ($atual -ne $Python) {
        if ($atual -eq "") { $atual = "desconhecido" }
        Fail "conflito: .venv usa Python $atual e o pedido é ${Python}: apague .venv (Remove-Item -Recurse -Force .venv) e rode de novo."
    }
} else {
    Write-Output "> criando o .venv com Python $Python"
    & $Uv venv --python $Python .venv
    if ($LASTEXITCODE -ne 0) { Fail "uv venv falhou (código $LASTEXITCODE)." }
}

Write-Output "> instalando o pacote em modo editável ($(Get-PackageTarget))"
& $Uv pip install --python $VenvPy -e (Get-PackageTarget)
if ($LASTEXITCODE -ne 0) { Fail "uv pip install falhou (código $LASTEXITCODE)." }

if (Test-Path -LiteralPath "web\package.json") {
    Write-Output "> construindo web/"
    & npm --prefix web ci
    if ($LASTEXITCODE -ne 0) { Fail "npm ci falhou (código $LASTEXITCODE)." }
    & npm --prefix web run build
    if ($LASTEXITCODE -ne 0) { Fail "npm run build falhou (código $LASTEXITCODE)." }
} else {
    Write-Output "web/ chega com a #34: nada a construir."
}

Write-Output "> checando o ambiente (simplicio-video doctor)"
& $Sv doctor
if ($LASTEXITCODE -ne 0) {
    Fail "o doctor apontou falhas acima. Corrija a correção indicada e rode $Sv doctor."
}

Write-Output ""
Write-Output "instalação pronta. Próximos passos:"
Write-Output "  $Sv install     copia a skill para o agente deste projeto (--global: para o home; --check mostra o plano)"
Write-Output "  $Sv setup       primeira execução: workspace, tema, idioma (use --yes para os padrões)"
Write-Output "  $Sv doctor      checagem do ambiente (--json para máquinas)"
Write-Output "  $Sv --help      todos os comandos"
Write-Output "Atualizar depois: git pull e powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1 (o simplicio-video update de um checkout só diz isso)"
