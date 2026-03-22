#!/bin/bash
# Copy all backend results to dashboard public/data for static hosting
cp -v ../backend/results/*.json ./public/data/
echo "Results copied to dashboard/public/data/"
