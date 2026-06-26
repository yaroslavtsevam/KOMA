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

# 2. Clone or Update KOMA Repository
REPO_DIR="koma"
REPO_URL_SSH="git@github.com:yaroslavtsevam/KOMA.git"
REPO_URL_HTTPS="https://github.com/yaroslavtsevam/KOMA.git"

if [ -d "$REPO_DIR" ]; then
    echo -e "${YELLOW}Directory '$REPO_DIR' already exists. Updating repository...${NC}"
    git -C "$REPO_DIR" pull
else
    echo -e "${GREEN}Cloning KOMA repository...${NC}"
    if ! git clone "$REPO_URL_SSH" "$REPO_DIR"; then
        echo -e "${YELLOW}SSH clone failed or keys not set up. Trying HTTPS...${NC}"
        git clone "$REPO_URL_HTTPS" "$REPO_DIR"
    fi
fi

# 3. Configure web/.env
ENV_FILE="$REPO_DIR/web/.env"
ENV_EXAMPLE="$REPO_DIR/web/.env.example"

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${GREEN}Creating web/.env configuration...${NC}"
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
    else
        echo -e "${YELLOW}Warning: web/.env.example not found in repository. Creating a default configuration...${NC}"
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
    echo -e "${GREEN}web/.env configured successfully.${NC}"
else
    echo -e "${YELLOW}web/.env configuration already exists. Skipping env setup.${NC}"
fi

# 3.2 Ensure .env.default is present at root (required by Dockerfile)
DEFAULT_ENV_FILE="$REPO_DIR/.env.default"
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

# 3.3 Hardware Architecture Detection for Docling Service
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

# 4. Start KOMA Service
echo -e "${GREEN}Starting KOMA service using $DOCKER_COMPOSE_CMD...${NC}"
COMPOSE_ARGS="-f current.docker-compose.yml"
if [ "$ARCH" = "nvidia" ]; then
    COMPOSE_ARGS="$COMPOSE_ARGS -f docker-compose.nvidia.yml"
elif [ "$ARCH" = "rocm" ]; then
    COMPOSE_ARGS="$COMPOSE_ARGS -f docker-compose.rocm.yml"
fi

$DOCKER_COMPOSE_CMD $COMPOSE_ARGS up -d --build koma

echo -e "${BLUE}======================================================${NC}"
echo -e "${GREEN} SUCCESS: KOMA has been successfully installed & started!${NC}"
echo -e "${BLUE}======================================================${NC}"
echo -e "You can access the KOMA web interface at: ${GREEN}https://koma.durum-project.ru${NC}"
echo -e "Default credentials:"
echo -e "  - Username: ${YELLOW}admin${NC}"
echo -e "  - Password: ${YELLOW}admin${NC}"
echo -e "${BLUE}======================================================${NC}"
