#!/bin/bash
# Start script for Steamroller Tracker

# Load environment variables from .env if present
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Ensure logs directory exists
mkdir -p logs

# Run the tracker
python steamroller_tracker.py


