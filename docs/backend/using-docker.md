# Running The Backend In Docker

The backend service can run independently in Docker even though full plugin installation for Docker-based NetBox deployments is not documented yet.

## Pull And Run

```bash
docker pull emersonfelipesp/proxbox-api:latest
docker run -d --name proxbox-api -p 8800:8800 emersonfelipesp/proxbox-api:latest
```

## Notes

- Port `8800` is the default backend port expected by the sample configuration.
- If you publish a different port, make the same change in the `FastAPIEndpoint` object inside NetBox.
- If you front the container with TLS or a reverse proxy, configure the NetBox endpoint object accordingly.
