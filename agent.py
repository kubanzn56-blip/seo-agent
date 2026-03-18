import os
import json
import base64
import requests
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from dotenv import load_dotenv
from fpdf import FPDF
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from bs4 import BeautifulSoup

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
VALUESERP_KEY = os.getenv("VALUESERP_KEY")
FIRMA_NAZWA = os.getenv("FIRMA_NAZWA", "Firma")
FIRMA_URL = os.getenv("FIRMA_URL", "")
FRAZY = os.getenv("FRAZY", "").split(",")
EMAIL_WYSLIJ_DO = os.getenv("EMAIL_WYSLIJ_DO", "")
CREDENTIALS_B64 = os.getenv("CREDENTIALS_B64")
TOKEN_B64 = os.getenv("TOKEN_B64")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")


def get_gmail_service():
    creds = None
    if TOKEN_B64:
        token_data = json.loads(base64.b64decode(TOKEN_B64).decode())
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes"),
        )
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def sprawdz_pozycje(fraza):
    try:
        url = "https://api.valueserp.com/search"
        params = {
            "api_key": VALUESERP_KEY,
            "q": fraza,
            "location": "Poland",
            "gl": "pl",
            "hl": "pl",
            "num": 20
        }
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        wyniki = data.get("organic_results", [])
        pozycja = None
        konkurenci = []
        domena = FIRMA_URL.lower().replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
        for i, wynik in enumerate(wyniki):
            link = wynik.get("link", "")
            tytul = wynik.get("title", "")
            opis = wynik.get("snippet", "")
            if domena and domena in link.lower():
                pozycja = i + 1
            if i < 5:
                konkurenci.append({"pozycja": i + 1, "tytul": tytul, "link": link, "opis": opis})
        return {"fraza": fraza, "pozycja": pozycja, "top5": konkurenci}
    except Exception as e:
        return {"fraza": fraza, "pozycja": None, "top5": [], "blad": str(e)}


def generuj_rekomendacje(wyniki_pozycji):
    dane = json.dumps(wyniki_pozycji, ensure_ascii=False, indent=2)
    prompt = f"""Jestes ekspertem SEO. Analizujesz dane pozycjonowania dla firmy "{FIRMA_NAZWA}" (strona: {FIRMA_URL}).

Dane z Google dla analizowanych fraz:
{dane}

Napisz profesjonalny raport SEO po polsku zawierajacy:

1. PODSUMOWANIE WYKONAWCZE (2-3 zdania ogolnej oceny)

2. POZYCJE W GOOGLE
Dla kazdej frazy podaj aktualna pozycje i ocene.

3. ANALIZA KONKURENCJI
Co robi konkurencja lepiej? Jakie tytuly, opisy maja w top 3?

4. REKOMENDACJE (minimum 5 konkretnych dzialan)
Podaj konkretne, wykonalne kroki.

5. PRIORYTETY NA NASTEPNY TYDZIEN
3 najwazniejsze rzeczy do zrobienia.

Pisz konkretnie i profesjonalnie."""
    response = model.generate_content(prompt)
    return response.text.strip()


class PDFRaport(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        self.set_fill_color(0, 113, 227)
        self.rect(0, 0, 210, 18, 'F')
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(255, 255, 255)
        self.set_y(4)
        self.cell(0, 10, f"Raport SEO - {FIRMA_NAZWA}", align="C")
        self.set_text_color(0, 0, 0)
        self.ln(16)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"bizAgent | Strona {self.page_no()}", align="C")
        self.set_text_color(0, 0, 0)

    def sekcja_tytul(self, tekst):
        self.set_font("Helvetica", "B", 13)
        self.set_fill_color(245, 245, 247)
        self.set_text_color(0, 113, 227)
        self.cell(0, 10, tekst, ln=True, fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def dodaj_tekst(self, tekst):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(50, 50, 50)
        tekst_safe = tekst.encode("latin-1", errors="replace").decode("latin-1")
        self.multi_cell(0, 6, tekst_safe)
        self.ln(2)


def generuj_pdf(wyniki, rekomendacje):
    pdf = PDFRaport()
    pdf.add_page()
    data = datetime.datetime.now().strftime("%d.%m.%Y")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, f"Data raportu: {data}  |  Strona: {FIRMA_URL}", ln=True)
    pdf.cell(0, 6, f"Analizowane frazy: {len(wyniki)}", ln=True)
    pdf.ln(6)

    pdf.sekcja_tytul("Pozycje w Google")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(230, 240, 255)
    pdf.cell(100, 8, "Fraza kluczowa", border=1, fill=True)
    pdf.cell(40, 8, "Pozycja", border=1, fill=True, align="C")
    pdf.cell(50, 8, "Status", border=1, fill=True, align="C")
    pdf.ln()

    for w in wyniki:
        fraza = w["fraza"].strip()
        pozycja = w.get("pozycja")
        if pozycja:
            status = "Dobra" if pozycja <= 5 else ("Srednia" if pozycja <= 15 else "Slaba")
            poz_txt = str(pozycja)
            if pozycja <= 5:
                pdf.set_fill_color(220, 255, 220)
            elif pozycja <= 15:
                pdf.set_fill_color(255, 245, 200)
            else:
                pdf.set_fill_color(255, 220, 220)
        else:
            status = "Brak w top 20"
            poz_txt = ">20"
            pdf.set_fill_color(255, 220, 220)

        pdf.set_font("Helvetica", "", 10)
        fraza_safe = fraza.encode("latin-1", errors="replace").decode("latin-1")
        pdf.cell(100, 8, fraza_safe, border=1, fill=True)
        pdf.cell(40, 8, poz_txt, border=1, fill=True, align="C")
        pdf.cell(50, 8, status, border=1, fill=True, align="C")
        pdf.ln()

    pdf.ln(8)
    pdf.sekcja_tytul("Top 5 Konkurentow")
    for w in wyniki:
        fraza_safe = w["fraza"].strip().encode("latin-1", errors="replace").decode("latin-1")
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, f"Fraza: {fraza_safe}", ln=True)
        pdf.set_font("Helvetica", "", 9)
        for k in w.get("top5", []):
            tytul = k["tytul"].encode("latin-1", errors="replace").decode("latin-1")
            link = k["link"].encode("latin-1", errors="replace").decode("latin-1")
            pdf.set_text_color(80, 80, 80)
            pdf.cell(10, 6, f"#{k['pozycja']}", ln=False)
            pdf.set_text_color(0, 113, 227)
            pdf.cell(0, 6, tytul[:80], ln=True)
            pdf.set_text_color(120, 120, 120)
            pdf.cell(10, 5, "", ln=False)
            pdf.cell(0, 5, link[:90], ln=True)
            pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

    pdf.add_page()
    pdf.sekcja_tytul("Analiza i Rekomendacje AI")
    pdf.dodaj_tekst(rekomendacje)

    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 6, "Raport wygenerowany automatycznie przez bizAgent | bizagent.pl", ln=True, align="C")

    sciezka = f"/tmp/raport_seo_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    pdf.output(sciezka)
    return sciezka


def wyslij_email_z_pdf(sciezka_pdf):
    if not EMAIL_WYSLIJ_DO:
        print("  Brak EMAIL_WYSLIJ_DO — pomijam wysylanie.")
        return

    service = get_gmail_service()

    with open(sciezka_pdf, "rb") as f:
        pdf_data = f.read()

    msg = MIMEMultipart()
    msg["To"] = EMAIL_WYSLIJ_DO
    msg["Subject"] = f"Raport SEO — {FIRMA_NAZWA} — {datetime.datetime.now().strftime('%d.%m.%Y')}"

    body = f"""Dzien dobry,

W zalaczeniu przesylamy tygodniowy raport SEO dla strony {FIRMA_URL}.

Raport zawiera:
- Aktualne pozycje w Google dla sledzonych fraz
- Analize top 5 konkurentow
- Konkretne rekomendacje na nastepny tydzien

Pozdrawiamy,
Zespol bizAgent | bizagent.pl"""

    msg.attach(MIMEText(body, "plain", "utf-8"))

    part = MIMEBase("application", "octet-stream")
    part.set_payload(pdf_data)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment; filename=raport_seo.pdf")
    msg.attach(part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"  Raport wyslany na: {EMAIL_WYSLIJ_DO}")


def uruchom_agenta():
    print(f"\nSEO Agent — {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print(f"Firma: {FIRMA_NAZWA} | URL: {FIRMA_URL}")
    print(f"Analizuje {len(FRAZY)} fraz...")

    wyniki = []
    for fraza in FRAZY:
        fraza = fraza.strip()
        if not fraza:
            continue
        print(f"  Sprawdzam: '{fraza}'...")
        wynik = sprawdz_pozycje(fraza)
        print(f"    Pozycja: {wynik.get('pozycja', 'brak w top 20')}")
        wyniki.append(wynik)

    print("Generuje rekomendacje AI...")
    rekomendacje = generuj_rekomendacje(wyniki)

    print("Generuje PDF...")
    sciezka_pdf = generuj_pdf(wyniki, rekomendacje)
    print(f"  PDF: {sciezka_pdf}")

    print("Wysylam e-mail przez Gmail API...")
    wyslij_email_z_pdf(sciezka_pdf)

    print("Gotowe!")
    return sciezka_pdf


if __name__ == "__main__":
    uruchom_agenta()
