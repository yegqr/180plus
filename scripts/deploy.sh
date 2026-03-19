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

# 4. Build image and start DB + Redis first
echo -e "${YELLOW}🏗️  Building image and starting infrastructure...${NC}"
docker compose build
docker compose up -d pg_database redis_cache

# 5. Wait for Postgres to be ready
echo -e "${YELLOW}⏳ Waiting for database to be ready...${NC}"
RETRIES=30
until docker compose exec -T pg_database pg_isready -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-nmt_bot}" > /dev/null 2>&1; do
    RETRIES=$((RETRIES - 1))
    if [ "$RETRIES" -le 0 ]; then
        echo -e "${RED}❌ Database did not become ready in time!${NC}"
        exit 1
    fi
    sleep 2
done
echo -e "${GREEN}✅ Database is ready!${NC}"

# 6. Sync Postgres password with .env (self-heals if .env was ever overwritten with wrong password)
# Local socket auth inside the container bypasses password checks, so this always works.
DB_PASS=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)
DB_USER=$(grep '^POSTGRES_USER=' .env | cut -d= -f2-)
DB_USER="${DB_USER:-postgres}"
if [ -n "$DB_PASS" ]; then
    docker compose exec -T pg_database psql -U "$DB_USER" -c "ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASS}';" > /dev/null 2>&1 \
        && echo -e "${GREEN}✅ DB password synced!${NC}" \
        || echo -e "${YELLOW}⚠️  Could not sync DB password (may be fine if already correct).${NC}"
fi

# 8. Run migrations in a fresh one-off container (not exec into potentially crashing bot)
echo -e "${YELLOW}🗄️  Running database migrations...${NC}"
if ! docker compose run --rm bot alembic upgrade head; then
    echo -e "${YELLOW}⚠️ Migration failed. Attempting to fix schema sync...${NC}"
    docker compose run --rm bot alembic stamp 6de8e23ae988 && \
    docker compose run --rm bot alembic upgrade head || {
        echo -e "${RED}❌ Migration fix failed! Check alembic logs.${NC}"
        exit 1
    }
fi
echo -e "${GREEN}✅ Migrations complete!${NC}"

# 9. Start bot
echo -e "${YELLOW}🤖 Starting bot...${NC}"
docker compose up -d bot

echo -e "${GREEN}🚀 Deployment successful!${NC}"
echo -e "${YELLOW}ℹ️  Check logs using: ${NC}docker compose logs -f bot"
