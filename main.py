from fastapi import FastAPI
from fastapi.responses import FileResponse
from apscheduler.schedulers.background import BackgroundScheduler
from agent import uruchom_agenta
import uvicorn
import os

app = FastAPI(title="SEO Report Agent")
scheduler = BackgroundScheduler()
ostatni_pdf = None


@app.on_event("startup")
def start():
    scheduler.add_job(run_and_save, "cron", day_of_week="wed", hour=16, minute=39)
    scheduler.start()
    print("SEO Agent uruchomiony — raport co poniedzialek o 8:00.")


@app.on_event("shutdown")
def stop():
    scheduler.shutdown()


def run_and_save():
    global ostatni_pdf
    ostatni_pdf = uruchom_agenta()


@app.get("/")
def root():
    return {"status": "dziala", "info": "SEO Report Agent aktywny"}


@app.get("/run")
def run_now():
    global ostatni_pdf
    ostatni_pdf = uruchom_agenta()
    return {"status": "wykonano", "pdf": ostatni_pdf}


@app.get("/pobierz-raport")
def pobierz():
    global ostatni_pdf
    if ostatni_pdf and os.path.exists(ostatni_pdf):
        return FileResponse(ostatni_pdf, media_type="application/pdf", filename="raport_seo.pdf")
    return {"blad": "Brak raportu — uruchom /run najpierw"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
