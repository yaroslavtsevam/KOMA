#!/bin/bash
# ==============================================================================
# WSL2 MTU Configuration & Fix Script
# ==============================================================================
set -e

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}             WSL2 MTU Configuration Fix               ${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. Check if running inside WSL
if ! grep -qi "microsoft" /proc/version 2>/dev/null && ! grep -qi "microsoft" /proc/sys/kernel/osrelease 2>/dev/null; then
    echo -e "${RED}Error: This script is designed to run INSIDE a WSL2 Linux instance.${NC}"
    echo -e "If you are running on macOS or native Linux, you do not need this fix."
    exit 1
fi

# 2. Dynamically set eth0 MTU to 1350
echo -e "${GREEN}Applying temporary MTU fix (setting eth0 MTU to 1350)...${NC}"
if sudo ip link set dev eth0 mtu 1350; then
    echo -e "${GREEN}Temporary MTU fix applied successfully!${NC}"
    echo -e "Current network interfaces:"
    ip addr show eth0 | grep mtu
else
    echo -e "${RED}Failed to set MTU. Please ensure you have sudo privileges.${NC}"
    exit 1
fi

# 3. Configure wsl.conf for a permanent boot fix
WSL_CONF="/etc/wsl.conf"
echo -e "\n${GREEN}Configuring permanent fix in $WSL_CONF...${NC}"

if [ ! -f "$WSL_CONF" ]; then
    echo -e "[boot]\ncommand = ip link set dev eth0 mtu 1350" | sudo tee "$WSL_CONF" > /dev/null
    echo -e "${GREEN}Created $WSL_CONF with boot MTU command.${NC}"
else
    if grep -q "command[[:space:]]*=" "$WSL_CONF"; then
        if grep -q "mtu 1350" "$WSL_CONF"; then
            echo -e "${YELLOW}Permanent MTU command is already present in $WSL_CONF.${NC}"
        else
            echo -e "${RED}Warning: $WSL_CONF already contains a custom boot command.${NC}"
            echo -e "${YELLOW}Please manually add the following command to your [boot] section in $WSL_CONF:${NC}"
            echo -e "  ${BLUE}ip link set dev eth0 mtu 1350${NC}"
        fi
    else
        if grep -q "\[boot\]" "$WSL_CONF"; then
            # Inject command right below [boot]
            sudo sed -i '/\[boot\]/a command = ip link set dev eth0 mtu 1350' "$WSL_CONF"
            echo -e "${GREEN}Appended MTU command to existing [boot] section in $WSL_CONF.${NC}"
        else
            # Append boot section to the end of wsl.conf
            echo -e "\n[boot]\ncommand = ip link set dev eth0 mtu 1350" | sudo tee -a "$WSL_CONF" > /dev/null
            echo -e "${GREEN}Appended [boot] section with MTU command to $WSL_CONF.${NC}"
        fi
    fi
fi

echo -e "\n${BLUE}======================================================${NC}"
echo -e "${GREEN} SUCCESS: WSL2 MTU has been corrected!${NC}"
echo -e "${BLUE}======================================================${NC}"
echo -e "To ensure the permanent configuration is loaded next time, run:"
echo -e "  ${YELLOW}wsl --shutdown${NC} in Windows PowerShell, then restart WSL."
echo -e "${BLUE}======================================================${NC}"
