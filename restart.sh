#!/bin/bash
pkill -f "uvicorn main:app --host 0.0.0.0 --port 3456" 2>/dev/null || true
sleep 1
python -m uvicorn main:app --host 0.0.0.0 --port 3456 > /dev/null 2>&1 &
echo "Started uvicorn on port 3456"
