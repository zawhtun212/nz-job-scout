@echo off
title NZ Job Scout Worker
cd /d %~dp0
echo Starting NZ Job Scout Worker...
python scraper_worker.py
pause