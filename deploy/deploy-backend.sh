#!/bin/bash
# Usage: ./deploy-backend.sh <FRONTEND_URL>
# e.g.:  ./deploy-backend.sh https://seyarkai-frontend-337434518869.us-central1.run.app
set -euo pipefail

FRONTEND_URL=${1:?"Usage: $0 <FRONTEND_URL>"}

gcloud run deploy seyarkai-backend \
  --image=us-central1-docker.pkg.dev/project-6c036441-c06e-4a0b-bbf/seyarkai-images/backend:latest \
  --platform=managed \
  --region=us-central1 \
  --service-account=backend-runtime@project-6c036441-c06e-4a0b-bbf.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --cpu=1 --memory=512Mi --no-cpu-throttling \
  --min-instances=1 --max-instances=1 --timeout=3600 \
  --add-cloudsql-instances=project-6c036441-c06e-4a0b-bbf:us-central1:seyarkai-db \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=project-6c036441-c06e-4a0b-bbf,GOOGLE_CLOUD_LOCATION=us-central1,GOOGLE_GENAI_USE_VERTEXAI=true,GEMINI_MODEL_FAST=gemini-2.5-flash,GEMINI_MODEL_SMART=gemini-2.5-pro,VERTEX_SEARCH_LOCATION=global,VERTEX_SEARCH_DATA_STORE_ID=knowledge-store,JWT_EXPIRE_HOURS=12,MAX_LLM_CALLS_PER_STAGE=8,KNOWLEDGE_AGEING_DAYS=90,KNOWLEDGE_STALE_DAYS=180,CORS_ORIGINS=${FRONTEND_URL}" \
  --set-secrets="DATABASE_URL=db-url:latest,JWT_SECRET=jwt-secret:latest,GEMINI_API_KEY=gemini-api-key:latest"
