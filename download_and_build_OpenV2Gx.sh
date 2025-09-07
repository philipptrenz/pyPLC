#!/bin/sh

echo "Temporarily mounting FS"
mount -o remount,rw /

echo "Get build dependencies"
opkg update
opkg install make gcc

echo "Download OpenV2Gx"
wget https://github.com/uhi22/OpenV2Gx/archive/refs/heads/master.zip -O tmp.zip
unzip tmp.zip && rm tmp.zip
mv OpenV2Gx-master/ /data/OpenV2Gx
cd /data/OpenV2Gx/Release

echo "Build OpenV2Gx, this might take a while ..."
make
chmod +x /data/OpenV2Gx/Release/OpenV2G.exe

echo "Done"