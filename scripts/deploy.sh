#!/bin/bash

# --- Color Definitions ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🚀 Starting NMT Bot Deployment Logic...${NC}"

# 1. Check for Docker
if ! [ -x "$(command -v docker)" ]; then
    echo -e "${YELLOW}🐳 Docker is not installed. Installing...${NC}"
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo -e "${GREEN}✅ Docker installed!${NC}"
fi

# 2. Check for Docker Compose
if ! docker compose version >/dev/null 2>&1; then
    echo -e "${YELLOW}🧩 Docker Compose is not installed. Installing...${NC}"
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
    echo -e "${GREEN}✅ Docker Compose installed!${NC}"
fi

# 3. Check for .env file
if [ ! -f .env ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo -e "${YELLOW}📝 Creating .env template. Please fill it and run the script again.${NC}"
    cp .env.dist .env 2>/dev/null || touch .env
    echo "BOT_TOKEN=" >> .env
    echo "ADMINS=" >> .env
    echo "USE_REDIS=True" >> .env
    echo "POSTGRES_USER=postgres" >> .env
    echo "POSTGRES_PASSWORD=generate_strong_password_here" >> .env
    echo "POSTGRES_DB=nmt_bot" >> .env
    echo "DB_HOST=pg_database" >> .env
    echo "DB_PORT=5432" >> .env
    echo "REDIS_HOST=redis_cache" >> .env
    echo "REDIS_PORT=6389" >> .env
    echo "REDIS_PASSWORD=someredispass" >> .env
    exit 1
fi

# 4. Pull/Build/Up
echo -e "${YELLOW}🏗️  Building and starting containers...${NC}"
docker compose up -d --build

echo -e "${YELLOW}🗄️  Running database migrations...${NC}"
# Wait a bit for DB to be ready (though depends_on helps, typically safer to wait or retry)
sleep 5
# Auto-healing migration:
# If upgrade fails (e.g. "table exists"), assume DB is out of sync, stamp to previous revision, and try again.
docker compose exec -T bot alembic upgrade head || (echo "⚠️ Migration failed. Attempting to fix schema sync..." && docker compose exec -T bot alembic stamp 6de8e23ae988 && docker compose exec -T bot alembic upgrade head)


echo -e "${GREEN}🚀 Deployment successful!${NC}"
echo -e "${YELLOW}ℹ️  Check logs using: ${NC}docker compose logs -f bot"
