#!/bin/bash

# Download and install wkhtmltopdf static build for Linux
echo "Downloading wkhtmltopdf..."
mkdir -p /tmp/wkhtmltopdf

curl -L https://github.com/wkhtmltopdf/wkhtmltopdf/releases/download/0.12.6/wkhtmltox-0.12.6-1.alpine3.17_amd64.apk -o /tmp/wkhtmltopdf/wkhtmltopdf.apk

# Extract the APK (which is just a tar.gz archive)
cd /tmp/wkhtmltopdf
tar -xzf wkhtmltopdf.apk || true  # tar won't work here; this is where the format failed

# Instead, download this known good archive:
curl -L https://github.com/wkhtmltopdf/wkhtmltopdf/releases/download/0.12.6/wkhtmltox-0.12.6_linux-generic-amd64.tar.xz -o /tmp/wkhtmltopdf/wkhtmltopdf.tar.xz

# Extract it
tar -xf /tmp/wkhtmltopdf/wkhtmltopdf.tar.xz -C /tmp/wkhtmltopdf

# Copy the binary to /usr/local/bin
cp /tmp/wkhtmltopdf/wkhtmltox/bin/wkhtmltopdf /usr/local/bin/wkhtmltopdf
chmod +x /usr/local/bin/wkhtmltopdf

# Confirm installed
which wkhtmltopdf
wkhtmltopdf --version
