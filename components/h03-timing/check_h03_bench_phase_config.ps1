param(
    [Parameter(Mandatory = $true)]
    [string]$Repo
)
$ErrorActionPreference = 'Stop'
$lfj8 = Join-Path $Repo 'targets\lfj8'
$gcc = 'C:\msys64\mingw64\bin\gcc.exe'
$m32rGcc = (Join-Path $PSScriptRoot '..\..\tools\SysGCC-m32r-elf-4.8.0\bin\m32r-elf-gcc.exe')
$m32rRun = Join-Path (Split-Path -Parent $m32rGcc) 'm32r-elf-run.exe'
$m32rFlags = @('-m32r', '-mmodel=medium', '-msdata=none', '-Wa,-EB')
$crt = (& $m32rGcc @m32rFlags '-print-file-name=crt0.o').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $crt)) { throw 'M32R startup unavailable' }
$flags = @('-std=c11', '-Os', '-Wall', '-Wextra', '-Werror', '-ffunction-sections', '-fdata-sections')
$include = @('-I', $lfj8, '-I', (Join-Path $Repo 'controller\include'), '-I', (Join-Path $Repo 'controller\vendor\toyota\include'), '-I', (Join-Path $Repo 'diagnostics'))
$sources = @(
    (Join-Path $PSScriptRoot 'test_h03_bench_phase_config.c'),
    (Join-Path $lfj8 'lfj8_h03_phase_startup.c'),
    (Join-Path $lfj8 'lfj8_h03_phase_clock.c'),
    (Join-Path $lfj8 'lfj8_h03_takeover.c'),
    (Join-Path $lfj8 'lfj8_h03_outputs.c'),
    (Join-Path $Repo 'controller\vendor\toyota\src\factory_core.c')
)
$previousPath = $env:Path
try {
$env:Path = (Split-Path -Parent $gcc) + ';' + $previousPath
foreach ($variant in @('before', 'after')) {
    $active = Join-Path $PSScriptRoot $variant
    $hostExe = Join-Path $active 'phase-host.exe'
    $targetElf = Join-Path $active 'phase-m32r.elf'
    & $gcc @flags '-I' $active @include @sources '-Wl,--gc-sections' '-o' $hostExe
    if ($LASTEXITCODE -ne 0) { throw "Host compilation failed for $variant" }
    & $m32rGcc @m32rFlags @flags '-I' $active @include '-nostartfiles' $crt @sources '-Wl,--gc-sections' '-Wl,--start-group' '-lc' '-lgloss' '-lgcc' '-Wl,--end-group' '-o' $targetElf
    if ($LASTEXITCODE -ne 0) { throw "M32R compilation failed for $variant" }
    $hostLog = & $hostExe
    $hostExit = $LASTEXITCODE
    $targetLog = & $m32rRun $targetElf
    $targetExit = $LASTEXITCODE
    "$variant host: $hostLog"
    "$variant M32R: $targetLog"
    if ($variant -eq 'before') {
        if ($hostExit -ne 1 -or $targetExit -ne 1 -or
            "$hostLog" -notmatch 'age=5000 command=10000 startup=0' -or
            "$targetLog" -notmatch 'age=5000 command=10000 startup=0') {
            throw 'The old profile must reproduce the startup failure'
        }
    } elseif ($hostExit -ne 0 -or $targetExit -ne 0) {
        throw 'The corrected profile failed a phase boundary test'
    }
}

} finally {
    $env:Path = $previousPath
}

