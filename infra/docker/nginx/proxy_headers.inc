proxy_set_header Host $host;
# nginx is the edge: overwrite (not append) so a client cannot fake its IP for rate limits.
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
