#!/bin/bash
set -euo pipefail

# PR-1 Validation Script (Ops endpoints)
# Uses:
#   DENIS_BASE_URL (default: http://127.0.0.1:9999)

echo "=== PR-1 Validation: Ops Endpoints ==="
echo ""

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=denis_env.sh
source "$HERE/denis_env.sh"

BASE_URL="$(denis_base_url)"
echo "DENIS_BASE_URL=$BASE_URL"
echo ""

if ! denis_is_reachable; then
    denis_print_unreachable
    echo "SKIP: server unreachable"
    exit 0
fi

# Test 1: /health
echo "Test 1: GET /health"
response=$(curl -s -w "\n%{http_code}" "$BASE_URL/health")
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    echo "✅ Status: 200 OK"
    echo "Response: $body"
    
    # Check required fields
    if echo "$body" | grep -q "status" && echo "$body" | grep -q "timestamp"; then
        echo "✅ Required fields present"
    else
        echo "❌ Missing required fields"
        exit 1
    fi
else
    echo "❌ Status: $http_code"
    echo "Response: $body"
    exit 1
fi

echo ""

# Test 2: /hass/entities
echo "Test 2: GET /hass/entities"
response=$(curl -s -w "\n%{http_code}" "$BASE_URL/hass/entities")
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    echo "✅ Status: 200 OK"
    
    # Check required fields
    if echo "$body" | grep -q "entities" && echo "$body" | grep -q "count"; then
        echo "✅ Required fields present"
        count=$(echo "$body" | grep -o '"count":[0-9]*' | cut -d':' -f2)
        echo "Entity count: $count"
    else
        echo "❌ Missing required fields"
        exit 1
    fi
else
    echo "❌ Status: $http_code"
    exit 1
fi

echo ""

# Test 3: /telemetry (JSON)
echo "Test 3: GET /telemetry (JSON)"
response=$(curl -s -w "\n%{http_code}" "$BASE_URL/telemetry")
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    echo "✅ Status: 200 OK"
    
    # Check required fields
    if echo "$body" | grep -q "requests" && echo "$body" | grep -q "async"; then
        echo "✅ Required fields present"
    else
        echo "❌ Missing required fields"
        exit 1
    fi
else
    echo "❌ Status: $http_code"
    exit 1
fi

echo ""

# Test 4: /telemetry (Prometheus)
echo "Test 4: GET /telemetry (Prometheus format)"
response=$(curl -s -w "\n%{http_code}" -H "Accept: text/plain" "$BASE_URL/telemetry")
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    echo "✅ Status: 200 OK"
    
    # Check Prometheus format
    if echo "$body" | grep -q "denis_requests_total"; then
        echo "✅ Prometheus format valid"
    else
        echo "❌ Invalid Prometheus format"
        exit 1
    fi
else
    echo "❌ Status: $http_code"
    exit 1
fi

echo ""
echo "=== All tests passed! ==="
echo ""
echo "Next steps:"
echo "1. Enable DENIS_CHAT_CP_GRAPH_WRITE=1"
echo "2. Run: MATCH (d:Decision) WHERE d.endpoint IN ['/health', '/hass/entities', '/telemetry'] RETURN count(d)"
echo "3. Verify DecisionTrace is written"
