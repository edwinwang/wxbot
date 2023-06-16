import os
import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv; load_dotenv()
import bot


app = FastAPI()

app.include_router(bot.router)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("host", "127.0.0.1"),
        port=int(os.getenv("port", "6000")),
        loop='asyncio',
    )
