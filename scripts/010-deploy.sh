#!/bin/bash

set -u
set -e

# directory and branch of git repository with source data for jekyll.  
# Note: relative to parent directory, not to this directory (scripts/).
SOURCE_REPO='source'
SOURCE_BRANCH='pages-source'

# directory and branch of git repository to commit output to.
# Note: relative to parent directory, not to this directory (scripts/).
TARGET_REPO='target'
TARGET_BRANCH='gh-pages'

TMP_DIR=$(realpath $(mktemp -d --tmpdir=.))

# pull source
cd $SOURCE_REPO
#git checkout $SOURCE_BRANCH
git pull

# build site (ends up in _site)

## Note that arguments of this script are passed to jekyll, this is used to call --full-rebuild
jekyll build $*
# --full-rebuild
#/var/lib/gems/2.0.0/gems/jekyll-2.5.3/bin/jekyll build

# copy site to temporary directory
cd -
rm -rf $TMP_DIR
cp -R $SOURCE_REPO/_site $TMP_DIR

# switch to target repo and clear
cd $TARGET_REPO
#git checkout $TARGET_BRANCH
rm -rf *

# copy in and remove temporary data
cd -
cp -r $TMP_DIR/* $TARGET_REPO
rm -rf $TMP_DIR

# commit and push
cd $TARGET_REPO
git add .
git commit -am 'autogenerated by https://github.com/spyysalo/jekyll-hook'
git push
