#!/bin/sh
set -e

dockerize -template /app/nishbot.conf.tmpl:/app/nishbot.conf

exec supybot nishbot.conf
