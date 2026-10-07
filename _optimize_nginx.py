import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.30.169', username='grudd420', password='123456', timeout=10)

def run(cmd, use_sudo=False):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    if use_sudo:
        stdin.write('123456\n')
        stdin.flush()
    out = stdout.read().decode(errors='replace').strip()
    err = stderr.read().decode(errors='replace').strip()
    return out, err

# Optimized Nginx config
nginx_conf = r"""server {
    listen 80 default_server;
    server_name _;
    client_max_body_size 20M;

    # ── Gzip Compression ──
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 5;
    gzip_min_length 256;
    gzip_types
        text/plain text/css text/xml text/javascript
        application/json application/javascript application/xml
        application/x-javascript application/xhtml+xml
        font/woff2 image/svg+xml;

    # ── Static files — aggressive caching ──
    location /static/ {
        alias /opt/ehr-africa/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;

        # Serve pre-compressed files if available
        gzip_static on;

        # CORS for fonts
        location ~* \.(woff2?|ttf|eot|otf)$ {
            add_header Access-Control-Allow-Origin *;
            expires 1y;
            add_header Cache-Control "public, immutable";
            access_log off;
        }
    }

    location /media/ {
        alias /opt/ehr-africa/media/;
        expires 30d;
        access_log off;
    }

    # ── WebSocket ──
    location /ws/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection upgrade;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }

    # ── Django app ──
    location / {
        proxy_pass http://ehr_upstream;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 5s;
        proxy_send_timeout 120s;
        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # Buffer responses — send to client in one shot
        proxy_buffering on;
        proxy_buffer_size 8k;
        proxy_buffers 8 16k;
        proxy_busy_buffers_size 32k;
    }
}

# ── Upstream with keepalive — reuse connections to Gunicorn ──
upstream ehr_upstream {
    server 127.0.0.1:8000;
    keepalive 16;
}

# Catch browsers trying HTTPS — redirect back to HTTP
server {
    listen 443 ssl default_server;
    server_name _;
    ssl_certificate     /etc/nginx/ssl/ehr.crt;
    ssl_certificate_key /etc/nginx/ssl/ehr.key;
    return 302 http://$host$request_uri;
}
"""

# Write config
out, err = run(f"echo '{nginx_conf}' | sudo -S tee /etc/nginx/sites-enabled/ehr > /dev/null 2>&1", use_sudo=True)

# Actually write it properly via a temp file
import tempfile, os

# Upload the config
sftp = ssh.open_sftp()
with sftp.open('/tmp/ehr_nginx.conf', 'w') as f:
    f.write(nginx_conf)
sftp.close()

# Copy to nginx config and test
out, err = run("sudo -S cp /tmp/ehr_nginx.conf /etc/nginx/sites-enabled/ehr 2>&1", use_sudo=True)
print("Config copied:", out, err)

out, err = run("sudo -S nginx -t 2>&1", use_sudo=True)
print("Nginx test:", out, err)

if 'successful' in (out + err):
    out, err = run("sudo -S systemctl reload nginx 2>&1", use_sudo=True)
    print("Nginx reloaded:", out, err)
    print("SUCCESS")
else:
    print("NGINX CONFIG ERROR - not reloading")
    # Restore original
    out, err = run("sudo -S nginx -t 2>&1", use_sudo=True)
    print("Current config status:", out, err)

ssh.close()
