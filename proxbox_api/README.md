# Installing proxbox-api (Plugin backend made using FastAPI)

## Using docker

### Pull the docker image

```
docker pull emersonfelipesp/proxbox-api:latest
```

### Run the container
```
docker run -d -p 8800:8800 --name proxbox-api emersonfelipesp/proxbox-api:latest
```