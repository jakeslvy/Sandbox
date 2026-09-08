Write-Host "Updating Personal Stats Dashboard..." -ForegroundColor Green

# Get the script directory and navigate to project root
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Split-Path -Parent $scriptDir)

# Render the dashboard
quarto render personal_stats/dashboard/src/personal_stats.qmd

Write-Host "Dashboard updated successfully!" -ForegroundColor Green
Read-Host "Press Enter to continue" 