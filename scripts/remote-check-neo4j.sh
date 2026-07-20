#!/bin/sh
set -eu

docker compose -f /opt/open-graph-memory/neo4j.yml exec -T neo4j sh -c \
    'username=${NEO4J_AUTH%%/*}; password=${NEO4J_AUTH#*/}; exec cypher-shell -u "$username" -p "$password" "MATCH (n) RETURN count(n) AS projected_nodes"'
