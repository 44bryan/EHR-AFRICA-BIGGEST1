#!/bin/bash
# Full browser simulation test for pagination

# Get CSRF token and session cookie
CSRF=$(curl -s -c /tmp/test_jar.txt http://localhost/accounts/login/ | grep csrfmiddlewaretoken | head -1 | sed 's/.*value="//' | sed 's/".*//')
echo "CSRF token: ${CSRF:0:20}..."

# Login
curl -s -c /tmp/test_jar.txt -b /tmp/test_jar.txt \
  -d "username=admin&password=Admin2026&csrfmiddlewaretoken=$CSRF" \
  -H "Referer: http://localhost/accounts/login/" \
  -L -o /dev/null -w "Login: %{http_code}\n" http://localhost/accounts/login/

# Test patients page 1
curl -s -b /tmp/test_jar.txt -o /tmp/p1.html -w "Page 1: %{http_code}\n" http://localhost/patients/
grep -o "Page [0-9]* of [0-9]*" /tmp/p1.html

# Test patients page 2
curl -s -b /tmp/test_jar.txt -o /tmp/p2.html -w "Page 2: %{http_code} redirect=%{redirect_url}\n" "http://localhost/patients/?page=2"
grep -o "Page [0-9]* of [0-9]*" /tmp/p2.html

# Check pagination links
echo "--- Pagination links ---"
grep -oP 'href="[^"]*page=[^"]*"' /tmp/p1.html | head -5

# Check wrapper div
echo "--- Wrapper div ---"
grep -o 'id="wrapper"[^>]*' /tmp/p1.html

# Check if hx-boost exists anywhere in the page
echo "--- hx-boost count ---"
grep -c 'hx-boost' /tmp/p1.html

# Pharmacy drugs page 2
curl -s -b /tmp/test_jar.txt -o /tmp/d2.html -w "Drugs page 2: %{http_code} redirect=%{redirect_url}\n" "http://localhost/pharmacy/drugs/?page=2"
grep -o "Page [0-9]* of [0-9]*" /tmp/d2.html
