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
- For HTTPS in local or staging environments, use `emersonfelipesp/proxbox-api:latest-nginx` and point the NetBox `FastAPIEndpoint` at `https://<host>:8800` with `verify_ssl` disabled (the mkcert cert is self-signed; tick enabled only after installing the mkcert root CA into NetBox's trust store).
- The backend image keeps nginx buffering off for `/stream` endpoints, so SSE progress stays chunked even when the service is proxied.
- To use your own CA-signed or Let's Encrypt certificate, mount it read-only at `/certs` (the directory must contain `cert.pem` and `key.pem`); mkcert generation is automatically skipped. With a trusted certificate you can also enable `verify_ssl` on the `FastAPIEndpoint`.
