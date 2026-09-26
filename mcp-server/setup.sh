#!/bin/bash
set -e

echo "============================================"
echo "🍿 AI Movie Planner - Setup Script"
echo "============================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_mark="${GREEN}✅${NC}"
cross_mark="${RED}❌${NC}"
warning_mark="${YELLOW}⚠️${NC}"

echo "Step 1: Checking Databricks CLI..."
if command -v databricks &> /dev/null; then
    echo -e "${check_mark} Databricks CLI installed"
    
    if databricks current-user me &> /dev/null; then
        echo -e "${check_mark} Databricks CLI authenticated"
    else
        echo -e "${cross_mark} Not authenticated. Run: databricks auth login"
        exit 1
    fi
else
    echo -e "${cross_mark} Databricks CLI not found. Install: pip install databricks-cli"
    exit 1
fi
echo ""

echo "Step 2: Checking Secrets..."
if databricks secrets get --scope database --key tmdb-api-key &> /dev/null; then
    echo -e "${check_mark} Secret 'database/tmdb-api-key' exists"
else
    echo -e "${warning_mark} Secret 'database/tmdb-api-key' not found"
    echo "   Create: databricks secrets put --scope database --key tmdb-api-key"
fi

if databricks secrets get --scope database --key lakebase-url &> /dev/null; then
    echo -e "${check_mark} Secret 'database/lakebase-url' exists"
else
    echo -e "${warning_mark} Secret 'database/lakebase-url' not found"
    echo "   Create: databricks secrets put --scope database --key lakebase-url"
fi
echo ""

echo "Step 3: Checking App..."
APP_NAME="mcp-server-ai-movie-planner"
if databricks apps get "$APP_NAME" --output JSON &> /dev/null; then
    echo -e "${check_mark} App exists"
else
    echo -e "${cross_mark} App not found: $APP_NAME"
fi
echo ""

echo "============================================"
echo "✅ Setup check complete!"
echo "============================================"
echo ""
echo "Next: Deploy the app"
echo "  databricks apps deploy $APP_NAME"
