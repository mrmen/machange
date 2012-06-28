#!/bin/bash

device=$(iwconfig 2>/dev/null | grep IEEE | awk '{print $1}')

if (($(echo $device | grep " "))); then
    echo "Too many devices… Modify script for having better results"
    echo "Try putting your favorite device in \"device\" variable and remove this test"
    exit 1
fi

if [ ! -e ~/.known_mac_address ]; then
    echo "~/.known_mac_address doesn't exist. Please create it and add your mac addresses"
    exit 1
fi

echo
echo "know mac addresses :"
echo
cat ~/.known_mac_address | awk -v var=1 '{print var"-" $0; var++}'
echo
echo "----------------------"
echo "Please choose one giving its line :"
read value

echo "you have choosen $(cat ~/.known_mac_address | awk '{print $1}' | head -n$value | tail -n1)"
new_mac_address="$(cat ~/.known_mac_address | awk '{print $2}' | head -n$value | tail -n1)"
echo 
echo "changing your mac address"

# part done as root
sudo ip link set dev $device down # push down interface
sudo ip link set dev $device address  $new_mac_address # set new mac address
sudo ip link set dev $device up  # push up interface


