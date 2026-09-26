#!/bin/bash
# Deploy AI Movie Night Planner MCP Server

set -e

echo "🚀 Deploying AI Movie Night Planner MCP Server..."
echo ""

# Navigate to MCP server directory
cd "$(dirname "$0")"

echo "📁 Current directory: $(pwd)"
echo ""

echo "✅ Files to deploy:"
ls -lh *.py *.yaml requirements.txt 2>/dev/null || true
echo ""

echo "🔧 Deploying with databricks CLI..."
databricks apps deploy mcp-server-ai-movie-planner

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Checking app status..."
databricks apps get mcp-server-ai-movie-planner

echo ""
echo "📝 Next steps:"
echo "  1. Wait ~30 seconds for the app to fully start"
echo "  2. Go to AI Playground: https://dbc-f27bef7b-a143.cloud.databricks.com/ml/playground"
echo "  3. Ask: 'who am I?'"
echo "  4. You should see: user_name: 'rajesh.kyreddy@gmail.com' (not the UUID!)"
echo ""
echo "🎉 If you see your email, the fix worked!"
