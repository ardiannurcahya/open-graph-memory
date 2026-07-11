#!/bin/sh
set -eu
scripts/lint.sh
scripts/test.sh
scripts/build.sh
