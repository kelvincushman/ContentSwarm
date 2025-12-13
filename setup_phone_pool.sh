#!/bin/bash
# Quick setup script for Phone Pool Manager

echo "=========================================="
echo "Phone Pool Manager - Quick Setup"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.10+"
    exit 1
fi

echo "✅ Python found: $(python3 --version)"
echo ""

# Check if ADB is installed
if ! command -v adb &> /dev/null; then
    echo "❌ ADB not found. Please install Android Platform Tools"
    echo "   macOS: brew install android-platform-tools"
    echo "   Linux: sudo apt install android-tools-adb"
    exit 1
fi

echo "✅ ADB found: $(adb version | head -n 1)"
echo ""

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt
pip install -e .
echo "✅ Dependencies installed"
echo ""

# Create sample phone config
if [ ! -f "phones_config.json" ]; then
    echo "📱 Creating sample phone configuration..."
    python3 phone_pool_cli.py --create-sample-config phones_config.json
    echo "✅ Created phones_config.json"
    echo ""
    echo "⚠️  Please edit phones_config.json with your actual phone IPs!"
    echo ""
else
    echo "ℹ️  phones_config.json already exists"
    echo ""
fi

# Check for connected devices
echo "📱 Checking for connected devices..."
DEVICE_COUNT=$(adb devices | grep -c "device$")

if [ "$DEVICE_COUNT" -gt 0 ]; then
    echo "✅ Found $DEVICE_COUNT connected device(s):"
    adb devices
else
    echo "❌ No devices connected"
    echo ""
    echo "To connect phones via WiFi:"
    echo "  1. Enable Developer Options on your phone"
    echo "  2. Enable USB Debugging"
    echo "  3. Enable Wireless Debugging"
    echo "  4. Run: adb connect <phone-ip>:5555"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Connect your phones:"
echo "   adb connect 192.168.1.100:5555"
echo "   adb connect 192.168.1.101:5555"
echo "   ..."
echo ""
echo "2. Edit phones_config.json with your phone IPs"
echo ""
echo "3. Start model service:"
echo "   python3 -m vllm.entrypoints.openai.api_server \\"
echo "     --model zai-org/AutoGLM-Phone-9B-Multilingual \\"
echo "     --port 8000 \\"
echo "     --gpu-memory-utilization 0.90 \\"
echo "     --max-model-len 8192"
echo ""
echo "   OR use third-party API (recommended for 20 phones)"
echo ""
echo "4. Launch Phone Pool Manager:"
echo "   python phone_pool_cli.py --config phones_config.json --lang en"
echo ""
echo "See PHONE_POOL_GUIDE.md for detailed instructions!"
echo ""
