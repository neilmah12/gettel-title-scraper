#!/bin/sh
# Builds the installable Tampermonkey script (gettel-title-scraper.user.js) from
# gettel-title-scraper.src.js. Some Tampermonkey builds fail on scripts longer
# than ~200 lines, so the installable file keeps the metadata header and puts
# the code on a single line. Requires: npm i terser
set -e
SRC=gettel-title-scraper.src.js
OUT=gettel-title-scraper.user.js
node -e "
const {minify}=require('terser');const fs=require('fs');
const src=fs.readFileSync('$SRC','utf8');
const marker='// ==/UserScript==';
const i=src.indexOf(marker)+marker.length;
minify(src.slice(i),{compress:true,mangle:true,format:{comments:false}}).then(r=>{
  if(r.error)throw r.error;
  fs.writeFileSync('$OUT',src.slice(0,i)+'\n'+r.code+'\n');
});"
