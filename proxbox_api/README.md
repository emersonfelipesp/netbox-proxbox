# Installing proxbox-api (Plugin backend made using FastAPI)

## Using docker (recommended)

### Pull the docker image

```
docker pull emersonfelipesp/proxbox-api:latest
```

### Run the container
```
docker run -d -p 8800:8800 --name proxbox-api emersonfelipesp/proxbox-api:latest
```

## Using git repository

### Clone the repository

```
git clone https://github.com/netdevopsbr/netbox-proxbox.git
```

### Change to 'proxbox_api' project root folder

```
cd proxbox_api 
```

### Install dependencies

```
pip install -r requirements.txt
```

### Change to 'proxbox_api' app folder (the actual code)

```
cd proxbox_api
```

### Start the FastAPI using astral-uv (recommended)

```
uv run fastapi run --host 0.0.0.0 --port 8800
```

- `--host 0.0.0.0` will make the app available on all host network interfaces, which my not be recommended.
Just pass your desired IP like `--host <YOUR-IP>` and it will also work.

- `--port 8800` is the default port, but you can change it if needed. Just to remember to update it on NetBox also, at FastAPI Endpoint model.

### If using 'uv' fails, try to start it directly:

Using `fastapi`:

```
pip install -e .
fastapi run --host 0.0.0.0 --port 8800
```

Or using `uvicorn`:

```
uvicorn main:app --host 0.0.0.0 --port 8800
```

## Using mkcert

Install the local CA in the system trust store.

```
mkcert -install
mkcert proxbox.backend.local localhost 127.0.0.1 ::1
```

With the keyfile and certfile generated, pass it on uvicorn command to start up FastAPI

### NGINX

```
sudo cp nginx.conf /etc/nginx/sites-available/proxbox
sudo ln -s -f /etc/nginx/sites-available/proxbox /etc/nginx/sites-enabled/proxbox
sudo systemctl restart nginx
```

```
/opt/netbox/venv/bin/uvicorn netbox-proxbox.proxbox_api.proxbox_api.main:app --host 0.0.0.0 --port 8800 --app-dir /opt/netbox/netbox --ssl-keyfile=localhost+2-key.pem --ssl-certfile=localhost+2.pem
```

Or 

```
cd /opt/netbox/netbox/netbox-proxbox/proxbox_api
uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800 --reload --ssl-keyfile=./proxbox_api/proxbox.backend.local+3-key.pem --ssl-certfile=./proxbox_api/proxbox.backend.local+3.pem
```