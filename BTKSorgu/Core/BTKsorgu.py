import uuid
import os
import re
from requests import Session
from parsel import Selector
from shutil import copyfileobj
from pytesseract import image_to_string
from PIL import Image
from os import remove
import pytesseract

# Tesseract yolu ayarlanıyor (Windows için varsayılan)
pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_PATH", r'C:\Program Files\Tesseract-OCR\tesseract.exe')

class BTKSorgu:
    def __init__(self, sorgu_url: str):
        self.ana_sayfa = "https://internet2.btk.gov.tr"
        self.sorgu_sayfasi = f"{self.ana_sayfa}/sitesorgu/"
        # Sadece domain adresini almak için regex
        domain = re.search(r"(?:https?://)?(?:www\.)?([^/]+)", sorgu_url)
        if not domain:
            raise ValueError("Geçerli bir URL girilmedi.")
        self.sorgu_url = domain.group(1)
        self._gecici_gorsel = f"captcha_{uuid.uuid4().hex}.png"
        self.oturum = Session()

    def __captcha_ver(self):
        try:
            print("[BTKSorgu] Captcha sayfası alınıyor...")
            ilk_bakis = self.oturum.get(self.sorgu_sayfasi)
            captcha_yolu = Selector(ilk_bakis.text).xpath("//div[@class='arama_captcha']/img/@src").get()

            if not captcha_yolu:
                print("[HATA] Captcha görsel yolu bulunamadı.")
                return None

            captcha_data = self.oturum.get(f"{self.ana_sayfa}{captcha_yolu}", stream=True)
            with open(self._gecici_gorsel, "wb") as f:
                copyfileobj(captcha_data.raw, f)

            return image_to_string(Image.open(self._gecici_gorsel)).strip().replace(" ", "")
        except Exception as e:
            print(f"[OCR Hatası] {e}")
            return None

    def karar_ver(self):
        captcha = self.__captcha_ver()
        if not captcha:
            return None

        try:
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
        except Exception as e:
            print(f"[POST Hatası] {e}")
            return None

    def __repr__(self):
        hatalar = [
            "Lütfen güvenlik kodunu giriniz.",
            "Güvenlik kodunu yanlış girdiniz.",
        ]
        try:
            for _ in range(5):
                html = self.karar_ver()
                if not html:
                    continue
                secici = Selector(html)
                hata = secici.xpath("//div[@class='icerik']/ul/li/text()").get()
                if hata and hata in hatalar:
                    print(f"[Captcha Hatası] {hata}, tekrar denenecek...")
                    continue

                ip = secici.xpath("//tr[td[contains(text(),'Sitenin IP')]]/td[2]/text()").get()
                ulke = secici.xpath("//tr[td[contains(text(),'Şehir/Ülke')]]/td[2]/text()").get()
                yersag = secici.xpath("//tr[td[contains(text(),'Yer Sağlayıcı')]]/td[2]/text()").get()
                erisimsag = secici.xpath("//tr[td[contains(text(),'Erişim Sağlayıcı')]]/td[2]/text()").get()
                karar = secici.xpath("//div[@class='yazi2']/text()").get() or secici.xpath("//span[@class='yazi2_2']/text()").get()

                return (
                    f"🔍 Alan adı: {self.sorgu_url}\n"
                    f"🌐 IP: {ip or 'Bilinmiyor'}\n"
                    f"📍 Ülke: {ulke or 'Bilinmiyor'}\n"
                    f"📡 Yer Sağlayıcı: {yersag or 'Bilinmiyor'}\n"
                    f"📡 Erişim Sağlayıcı: {erisimsag or 'Bilinmiyor'}\n"
                    f"⚖️ BTK Kararı: {karar or 'Bulunamadı'}"
                )
            return "⚠️ Maksimum captcha denemesi aşıldı."
        finally:
            if os.path.exists(self._gecici_gorsel):
                remove(self._gecici_gorsel)

    def __str__(self):
        return self.__repr__()
