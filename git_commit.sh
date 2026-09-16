#!/bin/bash
# ==============================================================================
# Git Commit & Push Prep Script for KOMA (Комплексный Оптимизатор Методических Актов)
# ==============================================================================

# Ensure script runs from the repository root
cd "$(dirname "$0")"

# Initialize Git if needed
if [ ! -d .git ]; then
    echo "Initializing new Git repository..."
    git init
    git branch -M main
fi

# Define remote URLs (using SSH for git push with SSH keys)
SSH_REMOTE="git@github.com:yaroslavtsevam/KOMA.git"

# Set or update remote origin
if git remote | grep -q "^origin$"; then
    echo "Updating remote origin URL to: $SSH_REMOTE"
    git remote set-url origin "$SSH_REMOTE"
else
    echo "Adding remote origin: $SSH_REMOTE"
    git remote add origin "$SSH_REMOTE"
fi

# Ensure branch is main
git branch -M main

# Add tracked files to staging
echo "Staging files..."
git add .gitignore
git add main.py
git add requirements.txt
git add algorithm.md
git add netbir_instructions.md
git add templates/
git add web/
git add agents/
git add tools/
git add schemas/
git add input/.gitkeep
git add processing/.gitkeep
git add results/.gitkeep

# Display staged files to verify .gitignore is working correctly
echo "--------------------------------------------------------"
echo "Files staged for commit:"
git status --short
echo "--------------------------------------------------------"

# Commit
COMMIT_MSG="Initial commit: Rebranded to KOMA and decoupled CLI/API architecture"
echo "Committing changes..."
git commit -m "$COMMIT_MSG"

echo ""
echo "========================================================"
echo " SUCCESS: Changes committed locally to branch 'main'!"
echo "========================================================"
echo "To push to GitHub, run:"
echo "  git push -u origin main"
echo "========================================================"
