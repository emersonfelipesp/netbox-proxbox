import uvicorn
from fastapi import FastAPI
from netbox_proxbox import proxbox_api

app = FastAPI()



@app.get("/full_update")
async def full_update():
    json_result = await proxbox_api.update.all()
    return json_result

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}