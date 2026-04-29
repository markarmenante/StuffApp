#!/bin/bash
cd "$(dirname "$0")"
pip install -q flask werkzeug 2>/dev/null
python app.py
