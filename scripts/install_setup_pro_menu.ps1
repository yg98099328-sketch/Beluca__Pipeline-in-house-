# BPE / setup_pro — .nuke\menu.py 비파괴 병합
# 기존 TD 파이프라인 menu.py 내용을 유지한 채 hook 만 추가합니다.
param(
    [string]$NukeHome = (Join-Path $env:USERPROFILE ".nuke"),
    [string]$TemplateMenu = ""
)

$ErrorActionPreference = "Stop"
$menuPath = Join-Path $NukeHome "menu.py"
$marker = "SETUP_PRO_BPE_MENU_HOOK_V1"

$hook = @"

# --- SETUP_PRO_BPE_MENU_HOOK_V1 (BPE install; existing menu.py preserved) ---
try:
    import nuke_setup_pro
    nuke_setup_pro.add_setup_pro_menu()
except Exception:
    pass
# --- end SETUP_PRO_BPE_MENU_HOOK_V1 ---
"@

if (-not (Test-Path -LiteralPath $menuPath)) {
    if ($TemplateMenu -and (Test-Path -LiteralPath $TemplateMenu)) {
        Copy-Item -LiteralPath $TemplateMenu -Destination $menuPath -Force
    }
    else {
        $minimal = @"
import nuke_setup_pro
nuke_setup_pro.add_setup_pro_menu()
"@
        Set-Content -LiteralPath $menuPath -Value $minimal.Trim() -Encoding UTF8
    }
    exit 0
}

$raw = ""
try {
    $raw = Get-Content -LiteralPath $menuPath -Raw -Encoding UTF8
}
catch {
    $raw = Get-Content -LiteralPath $menuPath -Raw
}
if ($null -eq $raw) { $raw = "" }

if ($raw -match [regex]::Escape($marker)) {
    exit 0
}

Add-Content -LiteralPath $menuPath -Value $hook -Encoding UTF8
exit 0
