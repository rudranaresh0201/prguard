#!/bin/bash
DB_PASS="Admin@123"
API_KEY="sk-prod-openai-key-abc123"
FILE=$1
cat $FILE | grep "error"
mysql -u root -p$DB_PASS -e "SELECT * FROM users WHERE id=$2"
eval "$3"
cp important_file.txt /backup/
rm important_file.txt
