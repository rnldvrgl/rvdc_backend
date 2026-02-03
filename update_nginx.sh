#!/bin/bash

# Quick script to update NGINX configuration with CORS headers
# Run this on your droplet: sudo bash update_nginx.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Updating NGINX configuration with CORS headers...${NC}"
echo ""

# Backup existing config
echo "Creating backup..."
cp /etc/nginx/sites-available/rvdc_backend /etc/nginx/sites-available/rvdc_backend.backup.$(date +%Y%m%d_%H%M%S)
echo -e "${GREEN}✓ Backup created${NC}"

# Update the config
cat > /etc/nginx/sites-available/rvdc_backend << 'EOF'
server {
    server_name api-rvdcrefandaircon.duckdns.org 206.189.157.123;

    # Increase upload size limit for profile images
    client_max_body_size 10M;

    location /static/ {
        alias /srv/rvdc_backend/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /srv/rvdc_backend/media/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        
        # CORS headers for media files
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range' always;
        
        # Handle OPTIONS preflight
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, OPTIONS';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/api-rvdcrefandaircon.duckdns.org/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/api-rvdcrefandaircon.duckdns.org/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot
}

# HTTP redirect to HTTPS
server {
    if ($host = api-rvdcrefandaircon.duckdns.org) {
        return 301 https://$host$request_uri;
    }

    listen 80;
    server_name api-rvdcrefandaircon.duckdns.org 206.189.157.123;
    return 404;
}
EOF

echo -e "${GREEN}✓ Configuration updated${NC}"

# Test configuration
echo ""
echo "Testing NGINX configuration..."
if nginx -t; then
    echo -e "${GREEN}✓ Configuration is valid${NC}"
    
    # Reload NGINX
    echo ""
    echo "Reloading NGINX..."
    systemctl reload nginx
    
    if systemctl is-active --quiet nginx; then
        echo -e "${GREEN}✓ NGINX reloaded successfully${NC}"
    else
        echo -e "${RED}✗ NGINX failed to reload${NC}"
        exit 1
    fi
else
    echo -e "${RED}✗ Configuration has errors${NC}"
    echo "Restoring backup..."
    cp /etc/nginx/sites-available/rvdc_backend.backup.* /etc/nginx/sites-available/rvdc_backend
    exit 1
fi

echo ""
echo "=========================================="
echo -e "${GREEN}NGINX Update Complete!${NC}"
echo "=========================================="
echo ""
echo "Changes made:"
echo "  ✓ Added CORS headers to /media/ location"
echo "  ✓ Added cache headers to static/media files"
echo "  ✓ Added HTTP to HTTPS redirect"
echo "  ✓ Increased client_max_body_size to 10M"
echo "  ✓ Added WebSocket support"
echo "  ✓ Added timeouts configuration"
echo ""
echo "Test your profile images now!"
echo ""
