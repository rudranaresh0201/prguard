#!/bin/bash
DB_PASSWORD="hardcoded123"
API_KEY="sk-prod-abc123xyz"
user_input=$1
query="SELECT * FROM users WHERE id=$user_input"
mysql -u root -p$DB_PASSWORD -e "$query"
eval "$2"
