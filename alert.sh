#!/bin/bash
# 报警投递: 写报警文件(每日一个) + 日志红标 (cron环境无mail命令, 落盘最可靠; 用户可通过文件/日志感知)
# 用法: alert.sh "TAG" "内容"
TAG="$1"; MSG="$2"
ALERT_DIR=/mnt/e/stockSurface/alerts
mkdir -p "$ALERT_DIR"
F="$ALERT_DIR/$(date +%Y%m%d).alert"
echo "[$(date '+%F %T')] $TAG: $MSG" >> "$F"
echo "ALERT $TAG: $MSG" >> /tmp/margin_daily.log
