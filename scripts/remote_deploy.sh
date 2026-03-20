#!/bin/bash

# --- Color Definitions ---
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${YELLOW}🛰️  Remote Deployment Script for NMT Bot${NC}"

CONFIG_FILE=".deploy_config"

# 1. Load Config if exists
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

# 2. Ask for Server Details (if not in config)
if [ -z "$SERVER_IP" ]; then
    read -p "Enter Server IP or Hostname: " SERVER_IP
    SERVER_IP=${SERVER_IP%/*}
fi

if [ -z "$SERVER_USER" ]; then
    read -p "Enter SSH Username (default: root): " SERVER_USER
    SERVER_USER=${SERVER_USER:-root}
fi

if [ -z "$TARGET_DIR" ]; then
    read -p "Enter Target Directory (default: ~/nmt-bot): " TARGET_DIR
    TARGET_DIR=${TARGET_DIR:-"~/nmt-bot"}
fi

# Save Config
echo "SERVER_IP=$SERVER_IP" > "$CONFIG_FILE"
echo "SERVER_USER=$SERVER_USER" >> "$CONFIG_FILE"
echo "TARGET_DIR=$TARGET_DIR" >> "$CONFIG_FILE"

# ============================================================
# STEP 1: Run tests
# ============================================================
echo ""
echo -e "${CYAN}${BOLD}┌─────────────────────────────────────────┐${NC}"
echo -e "${CYAN}${BOLD}│           🧪  Running tests...          │${NC}"
echo -e "${CYAN}${BOLD}└─────────────────────────────────────────┘${NC}"
echo ""

TEST_OUTPUT=$(python3 -m pytest -p no:warnings --tb=short -q 2>&1)
TEST_EXIT=$?

# Print only the progress dots + failures (no warnings block)
echo "$TEST_OUTPUT" | grep -v "^=\{3,\}\|^-\{3,\}\|warnings summary\|UserWarning\|DeprecationWarning\|warnings\.warn\|You may be able"
echo ""
echo -e "${CYAN}${BOLD}─────────────────────────────────────────${NC}"

# Extract summary line
SUMMARY=$(echo "$TEST_OUTPUT" | grep -E "passed|failed|error" | tail -1 | sed 's/, [0-9]* warning[s]*//')

if [ $TEST_EXIT -ne 0 ]; then
    echo -e "  ${RED}✗  $SUMMARY${NC}"
    echo ""
    echo -e "  ${RED}Deploy скасовано — виправте помилки і спробуйте знову.${NC}"
    echo -e "${CYAN}${BOLD}─────────────────────────────────────────${NC}"
    exit 1
fi

echo -e "  ${GREEN}✓  $SUMMARY${NC}"
echo -e "${CYAN}${BOLD}─────────────────────────────────────────${NC}"

# ============================================================
# STEP 2: Confirm
# ============================================================
echo ""
echo -e "${YELLOW}${BOLD}Продовжити деплой? Натисніть 'enter' для підтвердження:${NC} "
read -r CONFIRM

if [ "$CONFIRM" != "" ]; then
    echo -e "${YELLOW}⚠️  Деплой скасовано.${NC}"
    exit 0
fi

# ============================================================
# STEP 3: Git push
# ============================================================
echo ""
echo -e "${YELLOW}🐙 Committing and pushing to GitHub...${NC}"
git add .
if git diff-index --quiet HEAD --; then
    echo -e "${GREEN}📝 No changes to commit.${NC}"
else
    COMMIT_MSG="Auto-deploy commit: $(date +'%Y-%m-%d %H:%M:%S')"
    git commit -m "$COMMIT_MSG"

    echo -e "${YELLOW}⬆️  Pushing to remote repository...${NC}"
    git push
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Failed to push to GitHub. Continuing deployment anyway...${NC}"
    else
        echo -e "${GREEN}✅ Pushed to GitHub successfully!${NC}"
    fi
fi
echo ""

# ============================================================
# STEP 4: SSH + deploy
# ============================================================
echo -e "${YELLOW}🛸 Verifying SSH connection...${NC}"
echo -e "${YELLOW}ℹ️  If your password is expired, you will be asked to change it now.${NC}"

SSH_SOCKET="/tmp/ssh-$SERVER_USER-$SERVER_IP"
SSH_OPTIONS="-o ControlMaster=auto -o ControlPath=$SSH_SOCKET -o ControlPersist=10m"

trap "ssh -O exit -o ControlPath=$SSH_SOCKET $SERVER_USER@$SERVER_IP 2>/dev/null; rm -f $SSH_SOCKET" EXIT

ssh $SSH_OPTIONS -t "$SERVER_USER@$SERVER_IP" "echo '✅ SSH Connection verified! Proceeding to deployment...'"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ SSH Connection failed! Please check your credentials or internet connection.${NC}"
    exit 1
fi

echo -e "${YELLOW}📦 Syncing files to $SERVER_USER@$SERVER_IP:$TARGET_DIR...${NC}"

rsync -avz --exclude '.venv' \
      --exclude '__pycache__' \
      --exclude '.git' \
      --exclude '.idea' \
      --exclude '.vscode' \
      --exclude '.gemini' \
      --exclude 'pgdata' \
      --exclude 'cache_data' \
      --exclude '.env' \
      -e "ssh $SSH_OPTIONS" . "$SERVER_USER@$SERVER_IP:$TARGET_DIR"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to sync files! Check your SSH connection.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Sync complete!${NC}"
echo -e "${YELLOW}🚀 Executing remote deployment script...${NC}"

ssh $SSH_OPTIONS "$SERVER_USER@$SERVER_IP" "cd $TARGET_DIR && chmod +x scripts/deploy.sh && ./scripts/deploy.sh"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✨ Remote deployment finished successfully!${NC}"
    echo -e "${YELLOW}ℹ️  Your bot is now running on Hetzner.${NC}"
else
    echo -e "${RED}❌ Remote deployment failed! Check server logs.${NC}"
fi
