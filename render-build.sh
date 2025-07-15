#!/usr/bin/env bash

# Download and install wkhtmltopdf static binary
mkdir -p /tmp/wkhtmltopdf
curl -L https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6-1/wkhtmltox-0.12.6-1.linux-generic-amd64.tar.xz \
  | tar -xJ -C /tmp/wkhtmltopdf --strip-components=1

# Move binary to project root so it's available
cp /tmp/wkhtmltopdf/bin/wkhtmltopdf ./wkhtmltopdf

# Continue with normal build
pip install -r requirements.txt
