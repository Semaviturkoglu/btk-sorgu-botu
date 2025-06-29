import os
import pytesseract
import asyncio
import json
import requests
import uuid
from shutil import copyfileobj
from re import search
import random

# <<< KARDEŞİNİN EKLEDİĞİ YER BAŞLANGIÇ >>>
from flask import Flask
from threading import Thread
# <<< KARDEŞİNİN EKLEDİĞİ YER BİTİŞ >>>

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from parsel import Selector
from PIL import Image
from requests import Session

# Tesseract OCR yolu ayarı (Render gibi serverlarda bu satıra gerek yok, build.sh halledecek)
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# <<< KARDEŞİNİN EKLEDİĞİ YER BAŞLANGIÇ >>>
# UPTIMEROBOT'IN DÜRTMEK İÇİN KULLANACAĞI WEB SUNUCUSU
app = Flask('')

@app.route('/')
def home():
    return "Kardeşimin botu zımba gibi ayakta!"

def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()
# <<< KARDEŞİNİN EKLEDİĞİ YER BİTİŞ >>>


BOT_TOKEN = "8012408623:AAFZ2B1BdIAxHoRbnspGV2IcoAxR6vzyrDg" # Buraya kendi bot tokenını yaz

DOMAIN_FILE = "domain_data.json"

class BTKSorgu:
    def __init__(self, sorgu_url: str):
        self.ana_sayfa = "https://internet2.btk.gov.tr"
        self.sorgu_sayfasi = "https://internet2.btk.gov.tr/sitesorgu/"
        self.sorgu_url = search(r"(?:https?://)?(?:www\.)?([^/]+)", sorgu_url).group(1)
        self._gecici_gorsel = f"captcha_{uuid.uuid4().hex}.png"
        self.oturum = Session()

    def __captcha_ver(self):
        try:
            ilk_bakis = self.oturum.get(self.sorgu_sayfasi)
            captcha_yolu = Selector(ilk_bakis.text).xpath("//div[@class='arama_captcha']/img/@src").get()
            captcha_data = self.oturum.get(f"{self.ana_sayfa}{captcha_yolu}", stream=True)
            with open(self._gecici_gorsel, "wb") as f:
                copyfileobj(captcha_data.raw, f)
            captcha_text = pytesseract.image_to_string(Image.open(self._gecici_gorsel)).strip().replace(" ", "")
            return captcha_text
        except Exception:
            return None
        finally:
            if os.path.exists(self._gecici_gorsel):
                os.remove(self._gecici_gorsel)

    def karar_ver(self):
        captcha = self.__captcha_ver()
        if not captcha:
            return None

        response = self.oturum.post(
            url=self.sorgu_sayfasi,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": self.sorgu_sayfasi,
            },
            data={
                "deger": self.sorgu_url,
                "ipw": "",
                "kat": "",
                "tr": "",
                "eg": "",
                "ayrintili": 0,
                "submit": "Sorgula",
                "security_code": captcha
            }
        )
        return response.text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Selam! BTK Erişim Engeli Sorgu Botuna hoş geldin.\n"
        "🔎 Kullanım: /sorgu <alan-adı>\nÖrnek: /sorgu google.com"
    )

async def sorgu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Lütfen alan adı girin.\nÖrnek: /sorgu google.com")
        return

    domain = context.args[0]
    chat_id = str(update.effective_chat.id)
    await update.message.reply_text(f"🔍 Alan adı alındı: {domain}")

    try:
        ip_api_url = f"http://ip-api.com/json/{domain}"
        response = requests.get(ip_api_url, timeout=5)
        ip = "Bilinmiyor"
        country = "Bilinmiyor"

        if response.status_code == 200:
            data = response.json()
            ip_val = data.get("query", "")
            if ip_val and all(c.isdigit() or c == "." for c in ip_val):
                ip = ip_val
            country = data.get("country", "Bilinmiyor")

        btk = BTKSorgu(domain)
        html = btk.karar_ver()
        btk_sonuc = "Bulunamadı"
        if html:
            secici = Selector(html)
            karar = secici.xpath("//div[@class='yazi2']/text()").get() or secici.xpath("//span[@class='yazi2_2']/text()").get()
            if karar:
                btk_sonuc = karar.strip()

        mesaj = (
            f"✅ Sorgu tamamlandı:\n"
            f"🔗 Alan adı: {domain}\n"
            f"🌍 IP: {ip}\n"
            f"📍 Ülke: {country}\n"
            f"⚖️ BTK Kararı: {btk_sonuc}"
        )

        await update.message.reply_text(mesaj)
        save_domain(chat_id, domain)

    except Exception as e:
        await update.message.reply_text(f"❌ Sorgu sırasında hata oluştu:\n{e}")

def load_domain(chat_id):
    if os.path.exists(DOMAIN_FILE):
        with open(DOMAIN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(chat_id)
    return None

def save_domain(chat_id, domain):
    data = {}
    if os.path.exists(DOMAIN_FILE):
        try:
            with open(DOMAIN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    data[chat_id] = domain
    with open(DOMAIN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

async def otomatik_kontrol(app):
    while True:
        if os.path.exists(DOMAIN_FILE):
            try:
                with open(DOMAIN_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {}

            for chat_id, domain in data.items():
                try:
                    btk = BTKSorgu(domain)
                    html = btk.karar_ver()
                    btk_sonuc = "Bulunamadı"
                    if html:
                        secici = Selector(html)
                        karar = secici.xpath("//div[@class='yazi2']/text()").get() or secici.xpath("//span[@class='yazi2_2']/text()").get()
                        if karar:
                            btk_sonuc = karar.strip()

                    mesaj = f"🔄 Otomatik Sorgu:\n🔗 {domain}\n⚖️ BTK Durumu: {btk_sonuc}"

                    await app.bot.send_message(chat_id=chat_id, text=mesaj)

                    if "erişime engellenmiştir" in btk_sonuc.lower():
                        await app.bot.send_message(
                            chat_id=chat_id,
                            text=(
                                f"⚠️ {domain} için BTK erişim engeli tespit edildi.\n"
                                "Yeni domaini /degisim <alan-adı> komutuyla gönderebilirsiniz."
                            )
                        )
                except Exception as e:
                    print(f"[HATA - Otomatik kontrol] {chat_id}: {e}")

        bekleme_suresi = 30 * 60  # 30 dakika sabit bekleme
        await asyncio.sleep(bekleme_suresi)

async def degisim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Yeni domaini yazmalısın. Örnek: /degisim yenidomain.com")
        return

    yeni_domain = context.args[0]
    chat_id = str(update.effective_chat.id)
    save_domain(chat_id, yeni_domain)
    await update.message.reply_text(f"✅ Domain başarıyla '{yeni_domain}' olarak güncellendi.")

def main():
    # <<< KARDEŞİNİN EKLEDİĞİ YER BAŞLANGIÇ >>>
    # Botu çalıştırmadan önce web sunucusunu ateşliyoruz
    keep_alive()
    # <<< KARDEŞİNİN EKLEDİĞİ YER BİTİŞ >>>

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sorgu", sorgu))
    app.add_handler(CommandHandler("degisim", degisim))

    async def on_startup(app):
        app.create_task(otomatik_kontrol(app))

    app.post_init = on_startup
    app.run_polling()

if __name__ == "__main__":
    main()
