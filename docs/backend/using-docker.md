# Running The Backend In Docker

The backend service can run independently in Docker and pairs with the documented Docker-based NetBox plugin installation workflow.

## Pull And Run

```bash
docker pull emersonfelipesp/proxbox-api:latest
docker run -d --name proxbox-api -p 8800:8000 emersonfelipesp/proxbox-api:latest
```

## Notes

- Port `8800` is the default backend port expected by the sample configuration.
- The container exposes `8000` internally (nginx in front of uvicorn), so map host `8800` to container `8000`.
- If you publish a different port, make the same change in the `FastAPIEndpoint` object inside NetBox.
- If you front the container with TLS or a reverse proxy, configure the NetBox endpoint object accordingly.
- For HTTPS in local or staging environments, use `emersonfelipesp/proxbox-api:latest-mkcert` and point the NetBox `FastAPIEndpoint` at `https://<host>:8800` with `verify_ssl` enabled.
- The backend image keeps nginx buffering off for `/stream` endpoints, so SSE progress stays chunked even when the service is proxied.
