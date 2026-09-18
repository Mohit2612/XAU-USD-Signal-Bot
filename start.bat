@echo off
echo Building React App...
cd frontend
call npm run build
cd ..
echo Starting Unified API Server (which will also run the bot)...
python api.py
pause
