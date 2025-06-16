# PowerShell script to fetch and display current OI data

# Get current directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Add the script directory to the Python path
$env:PYTHONPATH = "$scriptDir;$env:PYTHONPATH"

Write-Host "Fetching current Nifty option OI data..."

# Run the Python script
try {
    python "$scriptDir\src\fetch_option_oi.py"
    Write-Host "Fetch complete."
} catch {
    Write-Host "Error fetching OI data: $_"
}

Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
