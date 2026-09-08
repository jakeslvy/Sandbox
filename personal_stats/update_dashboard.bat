@echo off
echo Updating Personal Stats Dashboard...
cd "C:\Users\JakeSelvey\Documents\GitHub\Sandbox"
cd ..
quarto render personal_stats\dashboard\src\personal_stats.qmd
echo Dashboard updated successfully!
pause 