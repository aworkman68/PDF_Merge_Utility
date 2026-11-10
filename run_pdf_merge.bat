@echo off
cd /d "%~dp0"
python pdf_merge_utility.py
if errorlevel 1 pause
