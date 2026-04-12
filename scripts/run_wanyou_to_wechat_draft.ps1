param(
    [switch]$PublicOnly,
    [switch]$WithLogin,
    [switch]$SkipDocx,
    [switch]$SkipAgentPayload,
    [switch]$DryRun,
    [string]$Cover = "",
    [string]$Title = "万有预报",
    [string]$Digest = "",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $Root

if (-not $PublicOnly -and -not $WithLogin) {
    $PublicOnly = $true
}

$runArgs = @("skills\wanyou-full-run\scripts\run_wanyou_full_run.py")
if ($WithLogin) {
    $runArgs += "--with-login"
} else {
    $runArgs += "--public-only"
}
if ($SkipDocx -or -not $PSBoundParameters.ContainsKey("SkipDocx")) {
    $runArgs += "--skip-docx"
}
if ($SkipAgentPayload) {
    $runArgs += "--skip-agent-payload"
}

Write-Host "[1/2] 运行万有预报完整生成流程... 输入统一认证用户名，回车后输入密码"
$pipelineOutput = & $Python @runArgs 2>&1
$pipelineOutput | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    throw "万有预报生成流程失败，退出码 $LASTEXITCODE"
}

$htmlPath = ""
$mdPath = ""
$runDir = ""
foreach ($line in $pipelineOutput) {
    $text = [string]$line
    if ($text -match '^html_path:\s*(.+)$') {
        $htmlPath = $Matches[1].Trim()
    }
    if ($text -match '^final_markdown_path:\s*(.+)$') {
        $mdPath = $Matches[1].Trim()
    }
    if ($text -match '^run_dir:\s*(.+)$') {
        $runDir = $Matches[1].Trim()
    }
    if (-not $htmlPath -and $text -match 'H5:\s*([^|]+)') {
        $htmlPath = $Matches[1].Trim()
    }
    if (-not $mdPath -and $text -match 'Markdown:\s*([^|]+)') {
        $mdPath = $Matches[1].Trim()
    }
}

if (-not $htmlPath -or -not (Test-Path $htmlPath)) {
    throw "未找到 HTML 输出路径，请确认完整流程未使用 --skip-html。"
}
if (-not $mdPath -or -not (Test-Path $mdPath)) {
    $candidate = [System.IO.Path]::ChangeExtension($htmlPath, ".md")
    if (Test-Path $candidate) {
        $mdPath = $candidate
    }
}

if (-not $Cover) {
    $htmlDir = Split-Path -Parent $htmlPath
    $candidateCovers = @(
        (Join-Path $htmlDir "_theme\badge.png"),
        (Join-Path $htmlDir "_theme\badge-mini.png")
    )
    foreach ($candidate in $candidateCovers) {
        if (Test-Path $candidate) {
            $Cover = $candidate
            break
        }
    }
}
if (-not $Cover -or -not (Test-Path $Cover)) {
    throw "未找到封面图。请用 -Cover 指定一张本地图片。"
}

Write-Host "[2/2] 保存到微信公众号草稿箱..."
$draftArgs = @(
    "scripts\publish_wechat_draft.py",
    $htmlPath,
    "--title", $Title
)
if ($Cover) {
    $draftArgs += @("--cover", $Cover)
}
if ($mdPath -and (Test-Path $mdPath)) {
    $draftArgs += @("--markdown", $mdPath)
}
if ($Digest) {
    $draftArgs += @("--digest", $Digest)
}
if ($DryRun) {
    $draftArgs += "--dry-run"
}

& $Python @draftArgs
if ($LASTEXITCODE -ne 0) {
    throw "保存微信公众号草稿失败，退出码 $LASTEXITCODE"
}
