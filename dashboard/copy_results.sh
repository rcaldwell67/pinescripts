#!/bin/bash
# Copy all backend results to dashboard public/data for static hosting
cp -v backend/results/*.json dashboard/public/data/
echo "Results copied to dashboard/public/data/"
