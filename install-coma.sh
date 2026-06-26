#!/bin/bash
# ==============================================================================
# KOMA Installation & Configuration Script
# ==============================================================================
set -e

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}       KOMA Installation & Configuration Script       ${NC}"
echo -e "${BLUE}======================================================${NC}"

# Ensure script runs from the directory where it is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# 1. Dependency Checks
if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is not installed. Please install git first.${NC}"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: docker is not installed. Please install docker first.${NC}"
    exit 1
fi

# Detect docker-compose variant
DOCKER_COMPOSE_CMD="docker compose"
if ! docker compose version &> /dev/null; then
    if command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker-compose"
    else
        echo -e "${RED}Error: Neither 'docker compose' nor 'docker-compose' is installed.${NC}"
        exit 1
    fi
fi

# Helper to read ini values
get_ini_val() {
    local file="$1"
    local key="$2"
    grep -i "^[[:space:]]*${key}[[:space:]]*=" "$file" | head -n 1 | cut -d'=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

# Helper to set/update variables in .env file
set_env_var() {
    local key="$1"
    local val="$2"
    local file=".env"
    if grep -q "^[[:space:]]*${key}[[:space:]]*=" "$file"; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^[[:space:]]*${key}[[:space:]]*=.*|${key}=${val}|g" "$file"
        else
            sed -i "s|^[[:space:]]*${key}[[:space:]]*=.*|${key}=${val}|g" "$file"
        fi
    else
        # Ensure file ends with a newline before appending
        if [ -f "$file" ] && [ -n "$(tail -c 1 "$file")" ]; then
            echo "" >> "$file"
        fi
        echo "${key}=${val}" >> "$file"
    fi
}

# 2. Configure .env file at the root
ENV_FILE=".env"
ENV_EXAMPLE="web/.env.example"

# 2.1 Ensure amnezia.config exists
if [ ! -f "amnezia.config" ]; then
    echo -e "${RED}Error: amnezia.config is missing at the repository root.${NC}"
    echo -e "${YELLOW}Please place your AmneziaWG configuration file in the project root as 'amnezia.config' and re-run this script.${NC}"
    exit 1
fi

# 2.2 Create .env from template if missing
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${GREEN}Creating .env configuration...${NC}"
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
    else
        echo -e "${YELLOW}Warning: web/.env.example not found. Creating a default configuration...${NC}"
        cat << 'EOF' > "$ENV_FILE"
# Google Gemini API key (required for the AI extraction pipeline)
GOOGLE_API_KEY=your_google_api_key_here

# Set to TRUE if using Vertex AI instead of Gemini API
GOOGLE_GENAI_USE_VERTEXAI=FALSE

# Secret key for NiceGUI session cookies – use a random 32-char string
STORAGE_SECRET=change-this-to-a-random-secret-key
EOF
    fi
    
    # Generate a random 32-character STORAGE_SECRET
    STORAGE_SECRET=$(openssl rand -hex 16 2>/dev/null || LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 32 || echo "koma_default_secret_32chars_long")
    
    # Retrieve GOOGLE_API_KEY (supports env variable, argument, or interactive prompt)
    API_KEY="${GOOGLE_API_KEY:-$1}"
    if [ -z "$API_KEY" ]; then
        if [ -t 0 ]; then
            echo -e "${YELLOW}Please enter your GOOGLE_API_KEY (for Gemini API):${NC}"
            read -r API_KEY
        else
            echo -e "${YELLOW}No GOOGLE_API_KEY was provided via arguments or env. The setup will continue, but you must manually update $ENV_FILE.${NC}"
        fi
    fi
    
    # Replace templates with actual values
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/STORAGE_SECRET=change-this-to-a-random-secret-key/STORAGE_SECRET=$STORAGE_SECRET/g" "$ENV_FILE"
        if [ -n "$API_KEY" ]; then
            sed -i '' "s/GOOGLE_API_KEY=your_google_api_key_here/GOOGLE_API_KEY=$API_KEY/g" "$ENV_FILE"
        fi
    else
        sed -i "s/STORAGE_SECRET=change-this-to-a-random-secret-key/STORAGE_SECRET=$STORAGE_SECRET/g" "$ENV_FILE"
        if [ -n "$API_KEY" ]; then
            sed -i "s/GOOGLE_API_KEY=your_google_api_key_here/GOOGLE_API_KEY=$API_KEY/g" "$ENV_FILE"
        fi
    fi
    echo -e "${GREEN}.env file initialized at the root.${NC}"
fi

# 2.3 Parse and write/update VPN settings from amnezia.config
echo -e "${GREEN}Parsing VPN parameters from amnezia.config...${NC}"
VPN_ADDRESS=$(get_ini_val "amnezia.config" "Address")
VPN_PRIVATE_KEY=$(get_ini_val "amnezia.config" "PrivateKey")
VPN_PUBLIC_KEY=$(get_ini_val "amnezia.config" "PublicKey")
VPN_PRESHARED_KEY=$(get_ini_val "amnezia.config" "PresharedKey")
VPN_ENDPOINT=$(get_ini_val "amnezia.config" "Endpoint")
VPN_ENDPOINT_IP=$(echo "$VPN_ENDPOINT" | cut -d':' -f1)
VPN_ENDPOINT_PORT=$(echo "$VPN_ENDPOINT" | cut -d':' -f2)
VPN_JC=$(get_ini_val "amnezia.config" "Jc")
VPN_JMIN=$(get_ini_val "amnezia.config" "Jmin")
VPN_JMAX=$(get_ini_val "amnezia.config" "Jmax")
VPN_S1=$(get_ini_val "amnezia.config" "S1")
VPN_S2=$(get_ini_val "amnezia.config" "S2")
VPN_H1=$(get_ini_val "amnezia.config" "H1")
VPN_H2=$(get_ini_val "amnezia.config" "H2")
VPN_H3=$(get_ini_val "amnezia.config" "H3")
VPN_H4=$(get_ini_val "amnezia.config" "H4")
VPN_KEEPALIVE=$(get_ini_val "amnezia.config" "PersistentKeepalive")
if [[ ! "$VPN_KEEPALIVE" =~ s$ ]] && [ -n "$VPN_KEEPALIVE" ]; then
    VPN_KEEPALIVE="${VPN_KEEPALIVE}s"
fi
VPN_MTU=$(get_ini_val "amnezia.config" "Mtu")
if [ -z "$VPN_MTU" ]; then
    VPN_MTU="1200"
fi

set_env_var "VPN_ADDRESS" "$VPN_ADDRESS"
set_env_var "VPN_PRIVATE_KEY" "$VPN_PRIVATE_KEY"
set_env_var "VPN_PUBLIC_KEY" "$VPN_PUBLIC_KEY"
set_env_var "VPN_PRESHARED_KEY" "$VPN_PRESHARED_KEY"
set_env_var "VPN_ENDPOINT_IP" "$VPN_ENDPOINT_IP"
set_env_var "VPN_ENDPOINT_PORT" "$VPN_ENDPOINT_PORT"
set_env_var "VPN_JC" "$VPN_JC"
set_env_var "VPN_JMIN" "$VPN_JMIN"
set_env_var "VPN_JMAX" "$VPN_JMAX"
set_env_var "VPN_S1" "$VPN_S1"
set_env_var "VPN_S2" "$VPN_S2"
set_env_var "VPN_H1" "$VPN_H1"
set_env_var "VPN_H2" "$VPN_H2"
set_env_var "VPN_H3" "$VPN_H3"
set_env_var "VPN_H4" "$VPN_H4"
set_env_var "VPN_PERSISTENT_KEEPALIVE" "$VPN_KEEPALIVE"
set_env_var "VPN_MTU" "$VPN_MTU"
echo -e "${GREEN}VPN configurations updated in .env successfully.${NC}"

# 3. Ensure .env.default is present at root (required by Dockerfile)
DEFAULT_ENV_FILE=".env.default"
if [ ! -f "$DEFAULT_ENV_FILE" ]; then
    echo -e "${YELLOW}Warning: .env.default not found in repository. Creating a default configuration...${NC}"
    cat << 'EOF' > "$DEFAULT_ENV_FILE"
# === DEFAULT PARAMETERS ===
course_type=профессиональное обучение
hours=72
year_of_study_start=2023
seminar_questions_number=15
control_questions_number=15
test_questions_number=15
lab_questions_number=15
project_questions_number=15
other_questions_number=15
EOF
fi

# 4. Hardware Architecture Detection for Docling Service
echo -e "${GREEN}Detecting hardware architecture...${NC}"
ARCH="cpu"

if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    echo -e "${GREEN}NVIDIA GPU detected. Using CUDA-accelerated Docling container.${NC}"
    ARCH="nvidia"
elif [ -c /dev/kfd ]; then
    echo -e "${GREEN}AMD GPU (ROCm) detected. Using ROCm-accelerated Docling container.${NC}"
    ARCH="rocm"
elif [[ "$(uname -s)" == "Darwin" ]]; then
    echo -e "${GREEN}Apple macOS detected. Using Apple/CPU Docling container.${NC}"
    ARCH="apple"
else
    echo -e "${YELLOW}No supported GPU detected. Falling back to standard CPU Docling container.${NC}"
    ARCH="cpu"
fi

# Build ROCm image locally if ROCm is detected but image is missing
if [ "$ARCH" = "rocm" ]; then
    if ! docker image inspect docling-serve-rocm:latest &> /dev/null; then
        echo -e "${YELLOW}ROCm image 'docling-serve-rocm:latest' not found locally. Cloning docling-serve and building locally...${NC}"
        git clone https://github.com/docling-project/docling-serve.git docling-serve-src
        make -C docling-serve-src docling-serve-rocm-image
        docker tag docling-serve-rocm:main docling-serve-rocm:latest
        rm -rf docling-serve-src
        echo -e "${GREEN}ROCm image built successfully.${NC}"
    fi
fi

# 5. Start KOMA Service
echo -e "${GREEN}Starting KOMA services using $DOCKER_COMPOSE_CMD...${NC}"
COMPOSE_ARGS="-f docker-compose.yml"
if [ "$ARCH" = "nvidia" ]; then
    COMPOSE_ARGS="$COMPOSE_ARGS -f docker-compose.nvidia.yml"
elif [ "$ARCH" = "rocm" ]; then
    COMPOSE_ARGS="$COMPOSE_ARGS -f docker-compose.rocm.yml"
fi

$DOCKER_COMPOSE_CMD $COMPOSE_ARGS up -d --build

echo -e "${BLUE}======================================================${NC}"
echo -e "${GREEN} SUCCESS: KOMA has been successfully installed & started!${NC}"
echo -e "${BLUE}======================================================${NC}"
echo -e "You can access the KOMA web interface at: ${GREEN}http://localhost:8080${NC}"
echo -e "Default credentials:"
echo -e "  - Username: ${YELLOW}admin${NC}"
echo -e "  - Password: ${YELLOW}admin${NC}"
echo -e "${BLUE}======================================================${NC}"
