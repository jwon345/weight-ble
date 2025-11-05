#!/bin/bash

python3 -m venv venv
source venv/bin/activate
pip3 install pip --upgrade
pip3 install -r requirements.txt

sudo touch /etc/systemd/system/weight.service && \
sudo bash -c "cat > /etc/systemd/system/weight.service <<EOF
[Unit]
Description=Weight BLE service
After=network.target

[Service]
Type=simple
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/run.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

systemctl enable weight.service
systemctl start weight.service