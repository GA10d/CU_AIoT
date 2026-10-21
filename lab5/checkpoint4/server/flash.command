#!/usr/bin/env bash
# Double-click this file in Finder to upload the server code to the ESP32 and show its boot output.
cd "$(dirname "$0")" && exec ./flash.sh --monitor
