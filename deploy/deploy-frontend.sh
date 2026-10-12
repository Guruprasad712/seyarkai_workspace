#!/bin/bash
# Usage: ./deploy-frontend.sh <BACKEND_URL>
# e.g.:  ./deploy-frontend.sh https://seyarkai-backend-337434518869.us-central1.run.app
# Note:  NEXT_PUBLIC_API_URL is a build-time arg — rebuild the image if the backend URL changes.
set -euo pipefail

gcloud run deploy seyarkai-frontend \
  --image=us-central1-docker.pkg.dev/project-6c036441-c06e-4a0b-bbf/seyarkai-images/frontend:latest \
  --platform=managed \
  --region=us-central1 \
  --allow-unauthenticated \
  --cpu=1 --memory=512Mi \
  --min-instances=1 --max-instances=1 --timeout=3600
