#!/bin/bash

set -x

if [ ! -z $TRAVIS_BRANCH ]; then
	export UPLOADTOOL_SUFFIX=$TRAVIS_BRANCH
fi

if [ "$TRAVIS_OS_NAME" = "linux" ]; then
	bash travis/upload.sh AppImage/Galacteek*.AppImage
fi

if [ "$TRAVIS_OS_NAME" = "osx" ]; then
	bash travis/upload.sh Galacteek*.dmg
fi

if [ "$TRAVIS_OS_NAME" = "windows" ]; then
	bash travis/upload.sh dist/galacteek*.exe
    # 7z a -tzip galacteek.zip build/galacteek
	# bash travis/upload.sh galacteek.zip
fi
