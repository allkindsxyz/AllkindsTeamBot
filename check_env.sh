#!/bin/bash
# Script to check environment variables for Railway deployment

echo "Checking environment variables for Railway deployment..."

# Check for required variables
required_vars=("BOT_TOKEN" "COMMUNICATOR_BOT_TOKEN" "DATABASE_URL")
missing=()

for var in "${required_vars[@]}"; do
  if [ -z "${!var}" ]; then
    missing+=("$var")
    echo "❌ Missing required variable: $var"
  else
    echo "✅ $var is set (starts with: ${!var:0:3}...)"
  fi
done

# Check optional variables
optional_vars=("COMMUNICATOR_BOT_USERNAME" "ADMIN_IDS" "OPENAI_API_KEY")

for var in "${optional_vars[@]}"; do
  if [ -z "${!var}" ]; then
    echo "⚠️ Optional variable not set: $var"
  else
    echo "✅ $var is set"
  fi
done

if [ ${#missing[@]} -gt 0 ]; then
  echo ""
  echo "Error: ${#missing[@]} required variables are missing!"
  echo "Please set them in Railway's environment variables settings."
  exit 1
else
  echo ""
  echo "All required variables are set!"
fi
