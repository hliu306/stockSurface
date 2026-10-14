#!/bin/bash
# 双击即启动(macOS): 本脚本会被 Finder 以 bash 执行
cd "$(dirname "$0")"
echo "replay 启动中..."
python3 serve_mac.py
