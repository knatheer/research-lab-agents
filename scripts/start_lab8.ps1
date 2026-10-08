# Opens one PowerShell window per service for the Lab 8 capstone.
# Run from the repo root:   powershell -ExecutionPolicy Bypass -File scripts\start_lab8.ps1
# Add -Local to also start the Mock Bank, Reviewer and Journal on your own machine
# (use this if the instructor's Journal is not reachable).

param([switch]$Local)

$root = Split-Path -Parent $PSScriptRoot
$services = @()
if ($Local) {
    $services += "services/mock_bank.py"
    $services += "instructor/reviewer_agent.py"
    $services += "instructor/journal.py"
}
$services += @(
    "solutions/lab07/paper_archive.py",
    "solutions/lab07/library_server.py",
    "solutions/lab05/verifier_agent.py",
    "solutions/lab06/experimenter_agent.py",
    "solutions/lab06/writer_agent.py",
    "solutions/lab08/publisher_agent.py"
)

foreach ($s in $services) {
    Start-Process powershell -WorkingDirectory $root -ArgumentList @(
        "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = '$s'; uv run python $s"
    )
    Start-Sleep -Seconds 2
}
Write-Host "Started $($services.Count) services. When all windows show their URL, run:"
Write-Host "    uv run python solutions/lab08/pi_full.py"
