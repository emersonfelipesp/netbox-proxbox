import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from netbox_proxbox import proxbox_api

app = FastAPI()

@app.get("/")
async def root(response_class=HTMLResponse):
    html_content = """
    <html>
        <head>
            <title>FastAPI | Home</title>
        </head>
        <body>
            <div align=center>
                <h1>FastAPI instance</h1>
                <p>It is running so <a href="https://github.com/netdevopsbr/netbox-proxbox" target="_blank">Proxbox</a> can use fome of the useful features like:
                    <br>
                    <br>
                        <strong>
                            <a href="https://fastapi.tiangolo.com/advanced/websockets/?h=websocket" target="_blank">
                                Websocket
                            </a>
                        </strong>
                    <br>
                        <strong>
                            <a href="https://fastapi.tiangolo.com/async/" target="_blank">
                                Assynchronous code (async / await)
                            </a>
                        </strong>
                    
                </p>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/full_update")
async def full_update():
    json_result = await proxbox_api.update.all()
    return json_result

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}