import os
import pytesseract
import asyncio
import json
import requests
import uuid
from shutil import copyfileobj
from re import search
import random

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes
from parsel import Selector
from PIL import Image
from requests import Session

# --- DEĞİŞKENLER ---
BOT_TOKEN = "8012408623:AAFZ2B1BdIAxHoRbnspGV2IcoAxR6vzyrDg"
# Render'daki Web Servisinin Ayarlar (Settings) -> Environment kısmından RENDER_APP_NAME adıyla bir değişken oluşturup,
# servis adını (URL'deki o https://<servis-adı>.onrender.com) oraya yaz.
RENDER_APP_NAME = os.getenv("RENDER_APP_NAME", "") 
PORT = int(os.environ.get('PORT', 8443))
WEBHOOK_URL = f"https://{RENDER_APP_NAME}.onrender.com/{BOT_TOKEN}"

# --- BOT KODLARI ---
DOMAIN_FILE = "domain_data.json"

class BTKSorgu:
    def __init__(self, sorgu_url: str):
        self.ana_sayfa = "https://internet2.btk.gov.tr"
        self.sorgu_sayfasi = "https://internet2.btk.gov.tr/sitesorgu/"
        self.sorgu_url = search(r"(?:https?://)?(?:www\.)?([^/]+)", sorgu_url).group(1)
        self._gecici_gorsel = f"/tmp/captcha_{uuid.uuid4().hex}.png"
        self.oturum = Session()

    def __captcha_ver(self):
        try:
            ilk_bakis = self.oturum.get(self.sorgu_sayfasi)
            captcha_yolu = Selector(ilk_bakis.text).xpath("//div[@class='arama_captcha']/img/@src").get()
            if not captcha_yolu: return None
            captcha_data = self.oturum.get(f"{self.ana_sayfa}{captcha_yolu}", stream=True)
            with open(self._gecici_gorsel, "wb") as f:
                copyfileobj(captcha_data.raw, f)
            captcha_text = pytesseract.image_to_string(Image.open(self._gecici_gorsel)).strip().replace(" ", "")
            return captcha_text
        except Exception as e:
            print(f"Captcha hatası: {e}")
            return None
        finally:
            if os.path.exists(self._gecici_gorsel):
                os.remove(self._gecici_gorsel)

    def karar_ver(self):
        captcha = self.__captcha_ver()
        if not captcha:
            print("Captcha çözülemedi.")
            return None
        response = self.oturum.post(
            url=self.sorgu_sayfasi,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": self.sorgu_sayfasi},
            data={"deger": self.sorgu_url, "ipw": "", "kat": "", "tr": "", "eg": "", "ayrintili": 0, "submit": "Sorgula", "security_code": captcha}
        )
        return response.text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Webhook ile çalışıyorum! Kullanım: /sorgu <alan-adı>")

async def sorgu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Lütfen alan adı girin.\nÖrnek: /sorgu google.com")
        return

    domain = context.args[0]
    await update.message.reply_text(f"🔍 Alan adı alındı: {domain}, sorgulanıyor...")
    try:
        # ... (sorgu fonksiyonunun geri kalanı aynı)
        btk = BTKSorgu(domain)
        html = btk.karar_ver()
        btk_sonuc = "Bulunamadı veya bir hata oluştu."
        if html:
            secici = Selector(html)
            karar = secici.xpath("//div[@class='yazi2']/text()").get() or secici.xpath("//span[@class='yazi2_2']/text()").get()
            if karar:
                btk_sonuc = karar.strip()
        await update.message.reply_text(f"✅ Sorgu tamamlandı:\n🔗 Alan adı: {domain}\n⚖️ BTK Kararı: {btk_sonuc}")
    except Exception as e:
        await update.message.reply_text(f"❌ Sorgu sırasında hata oluştu:\n{e}")

async def main() -> None:
    """Botu Webhook modunda başlatır."""
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Komutları ekliyoruz
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sorgu", sorgu))

    print(f"Webhook {WEBHOOK_URL} adresine kuruluyor...")
    await app.bot.set_webhook(url=WEBHOOK_URL, allowed_updates=Update.ALL_TYPES)
    
    print("Webhook sunucusu başlatılıyor...")
    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=WEBHOOK_URL,
    )
    print("Uygulama sunucusu durdu.")

if __name__ == "__main__":
    print("Bot Webhook modunda başlatılıyor...")
    asyncio.run(main())
