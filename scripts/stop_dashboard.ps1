# Stops ONLY this project's dashboard server, by the process id it wrote at startup (work\dashboard.pid).
# Never matches by name: other programs may also run "python app.py".
$pidFile = Join-Path $PSScriptRoot "..\work\dashboard.pid"
if (-not (Test-Path $pidFile)) { "No dashboard.pid: the dashboard is not running (or was started by an older version)."; exit 0 }
$id = [int](Get-Content $pidFile)
$p = Get-CimInstance Win32_Process -Filter "ProcessId=$id"
if ($p -and $p.CommandLine -like '*app.py*') {
    # the venv launcher is this process's parent; stop both so the port is freed
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ParentProcessId)"
    Stop-Process -Id $id -Force
    if ($parent -and $parent.CommandLine -like '*MTSU-Validation*app.py*') { Stop-Process -Id $parent.ProcessId -Force -ErrorAction SilentlyContinue }
    "Stopped the dashboard (pid $id)."
} else { "Process $id is not the dashboard any more; nothing stopped." }
Remove-Item $pidFile -ErrorAction SilentlyContinue
