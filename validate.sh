#!/bin/bash
# Quick validation script for Acoustic Alarm Detector add-on
# Run this before deploying to Home Assistant

echo "=========================================="
echo "Acoustic Alarm Detector - Pre-Flight Check"
echo "=========================================="
echo ""

ERRORS=0
WARNINGS=0

# Check 1: Directory structure
echo "✓ Checking directory structure..."
if [ ! -f "Dockerfile" ]; then
    echo "  ❌ ERROR: Dockerfile not found"
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ Dockerfile exists"
fi

if [ ! -f "config.yaml" ]; then
    echo "  ❌ ERROR: config.yaml not found"
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ config.yaml exists"
fi

if [ ! -f "run.sh" ]; then
    echo "  ❌ ERROR: run.sh not found"
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ run.sh exists"
    if [ ! -x "run.sh" ]; then
        echo "  ⚠️  WARNING: run.sh is not executable"
        WARNINGS=$((WARNINGS + 1))
    else
        echo "  ✓ run.sh is executable"
    fi
fi

if [ ! -f "requirements.txt" ]; then
    echo "  ❌ ERROR: requirements.txt not found"
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ requirements.txt exists"
    # Check if it contains Python packages
    if grep -q "FROM" requirements.txt; then
        echo "  ❌ ERROR: requirements.txt contains Dockerfile content!"
        ERRORS=$((ERRORS + 1))
    elif grep -q "pyaudio" requirements.txt; then
        echo "  ✓ requirements.txt looks valid"
    else
        echo "  ⚠️  WARNING: requirements.txt may be empty or invalid"
        WARNINGS=$((WARNINGS + 1))
    fi
fi

if [ ! -d "detector" ]; then
    echo "  ❌ ERROR: detector/ directory not found"
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ detector/ directory exists"
fi

echo ""

# Check 2: Python files
echo "✓ Checking Python files..."
PYTHON_FILES=(
    "detector/__init__.py"
    "detector/main.py"
    "detector/audio_detector.py"
    "detector/mqtt_client.py"
    "detector/config.py"
)

for file in "${PYTHON_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "  ❌ ERROR: $file not found"
        ERRORS=$((ERRORS + 1))
    else
        echo "  ✓ $file exists"
    fi
done

echo ""

# Check 3: Dockerfile validation
echo "✓ Checking Dockerfile..."
if grep -q "ARG BUILD_FROM" Dockerfile; then
    echo "  ✓ Uses BUILD_FROM pattern"
else
    echo "  ⚠️  WARNING: Missing ARG BUILD_FROM"
    WARNINGS=$((WARNINGS + 1))
fi

if grep -q "WORKDIR /app" Dockerfile; then
    echo "  ✓ Sets WORKDIR to /app"
else
    echo "  ⚠️  WARNING: WORKDIR not set to /app"
    WARNINGS=$((WARNINGS + 1))
fi

if grep -q "chmod.*run.sh" Dockerfile; then
    if grep -q "chmod.*\/app\/run.sh" Dockerfile; then
        echo "  ✓ chmod uses correct path (/app/run.sh)"
    else
        echo "  ❌ ERROR: chmod uses wrong path (should be /app/run.sh)"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "  ⚠️  WARNING: No chmod command for run.sh"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

# Check 4: config.yaml validation
echo "✓ Checking config.yaml..."
if grep -q "name:" config.yaml && grep -q "version:" config.yaml && grep -q "slug:" config.yaml; then
    echo "  ✓ Contains required fields (name, version, slug)"
else
    echo "  ❌ ERROR: Missing required fields in config.yaml"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "audio: true" config.yaml; then
    echo "  ✓ Audio access enabled"
else
    echo "  ⚠️  WARNING: audio: true not set"
    WARNINGS=$((WARNINGS + 1))
fi

if grep -q "/dev/snd" config.yaml; then
    echo "  ✓ Audio device mapping configured"
else
    echo "  ⚠️  WARNING: /dev/snd device mapping not found"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

# Check 5: run.sh validation
echo "✓ Checking run.sh..."
if grep -q "bashio::config" run.sh; then
    echo "  ✓ Uses bashio for configuration"
else
    echo "  ❌ ERROR: Missing bashio::config calls"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "python3.*main.py" run.sh; then
    echo "  ✓ Launches main.py"
else
    echo "  ❌ ERROR: Doesn't launch main.py"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# Summary
echo "=========================================="
echo "VALIDATION SUMMARY"
echo "=========================================="
echo "Errors:   $ERRORS"
echo "Warnings: $WARNINGS"
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo "✅ ALL CHECKS PASSED! Ready to deploy."
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo "⚠️  PASSED WITH WARNINGS. Review warnings above."
    exit 0
else
    echo "❌ VALIDATION FAILED! Fix errors before deploying."
    exit 1
fi
