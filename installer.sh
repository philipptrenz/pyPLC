#!/bin/sh

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SERVICE_NAME="pyPLC"

FILE=/data/rc.local
DESCRIPTION="Auto-reinstall $SERVICE_NAME"
COMMAND="ln -sf $SCRIPT_DIR/service /service/$SERVICE_NAME"


echo "Temporarily mounting FS"
mount -o remount,rw /

if [ -e ../OpenV2Gx/Release/OpenV2G ]; then
    chmod +x ../OpenV2Gx/Release/OpenV2G.exe
else
    echo "INSTALL FAILED: OpenV2Gx is missing, make sure that https://github.com/uhi22/OpenV2Gx is installed first"
    exit 1
fi

echo "Installing pip"
opkg update && opkg install python3-pip

echo "Installing pcap-ct via pip"
python3 -m pip install --upgrade pcap-ct

# Add auto-reinstall after Venus OS update, if not exists
grep -qF -- "$COMMAND" "$FILE" || {
    printf "# $DESCRIPTION\n${COMMAND}\n" >> $FILE
}
echo "done"

printf "Installing $SERVICE_NAME service ... "
$COMMAND
echo "done"

echo "Making files executable"
chmod +x $SCRIPT_DIR/service/run
chmod +x $SCRIPT_DIR/service/log/run

printf "Starting $SERVICE_NAME ... "
sync
t=10
until [ -d "/service/${SERVICE_NAME}/supervise" ] || (( t-- < 0 )); do
    sleep 1
done
if (( t < 0)); then
    echo "timeout!"
else
    svc -d /service/$SERVICE_NAME
    svc -u /service/$SERVICE_NAME
    echo "done"
fi
