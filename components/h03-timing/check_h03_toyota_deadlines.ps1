param(
    [Parameter(Mandatory = $true)]
    [string]$Repo
)
$ErrorActionPreference = 'Stop'
$lfj8 = Join-Path $Repo 'targets\lfj8'
$hostGcc = 'C:\msys64\mingw64\bin\gcc.exe'
$targetGcc = (Join-Path $PSScriptRoot '..\..\tools\SysGCC-m32r-elf-4.8.0\bin\m32r-elf-gcc.exe')
$targetRun = Join-Path (Split-Path -Parent $targetGcc) 'm32r-elf-run.exe'
$includes = @(
    '-I', $lfj8, '-I', (Join-Path $Repo 'controller\include'),
    '-I', (Join-Path $Repo 'controller\vendor\toyota\include'), '-I', (Join-Path $Repo 'diagnostics')
)
$sources = @(
    (Join-Path $PSScriptRoot 'test_h03_toyota_deadlines.c'),
    (Join-Path $lfj8 'lfj8_h03_toyota_source.c')
)
$flags = @('-std=c11', '-Os', '-Wall', '-Wextra', '-Werror')
$m32r = @('-m32r', '-mmodel=medium', '-msdata=none', '-Wa,-EB')
$crt = (& $targetGcc @m32r '-print-file-name=crt0.o').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $crt)) { throw 'M32R startup unavailable' }
$hostOutput = Join-Path $PSScriptRoot 'toyota-deadlines-host.exe'
$targetOutput = Join-Path $PSScriptRoot 'toyota-deadlines-m32r.elf'
$oldPath = $env:Path
try {
    $env:Path = (Split-Path -Parent $hostGcc) + ';' + $oldPath
    & $hostGcc @flags @includes @sources '-o' $hostOutput
    if ($LASTEXITCODE -ne 0) { throw 'Host build failed' }
    & $hostOutput
    if ($LASTEXITCODE -ne 0) { throw 'Host deadline test failed' }
} finally {
    $env:Path = $oldPath
}
& $targetGcc @m32r @flags @includes '-nostartfiles' $crt @sources '-Wl,--start-group' '-lc' '-lgloss' '-lgcc' '-Wl,--end-group' '-o' $targetOutput
if ($LASTEXITCODE -ne 0) { throw 'M32R build failed' }
& $targetRun $targetOutput
if ($LASTEXITCODE -ne 0) { throw 'M32R deadline test failed' }

