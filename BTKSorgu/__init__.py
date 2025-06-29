from requests import Session
from parsel import Selector
from shutil import copyfileobj
from pytesseract import image_to_string
import pytesseract
from PIL import Image
from re import search
from os import remove
from BTKSorgu.Core import BTKSorgu

# Eğer konsol modülün varsa, aşağıdaki satırı bırakabilirsin
# from ..Libs import konsol  

class BTKSorgu(object):
    def __init__(self, sorgu_url: str):
        # Tesseract'ın tam yolu - kendi bilgisayarındaki yol buysa kullan
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

        self.ana_sayfa = "https://internet2.btk.gov.tr"
        self.sorgu_sayfasi = "https://internet2.btk.gov.tr/sitesorgu/"
        self.sorgu_url = search(r"(?:https?://)?(?:www\.)?([^/]+)", sorgu_url).group(1)
        self._gecici_gorsel = "captcha.png"
        self.oturum = Session()

    def __captcha_ver(self):
        print("[BTKSorgu] Captcha sayfası isteniyor...")  # İstersen bu satırı bırakabilirsin
        ilk_bakis = self.oturum.get(self.sorgu_sayfasi, allow_redirects=True)
        captcha_yolu = Selector(ilk_bakis.text).xpath("//div[@class='arama_captcha']/img/@src").get()
        captcha_data = self.oturum.get(f"{self.ana_sayfa}{captcha_yolu}", stream=True)

        with open(self._gecici_gorsel, "wb") as captcha_gorsel:
            copyfileobj(captcha_data.raw, captcha_gorsel)

        try:
            captcha_harfleri = image_to_string(Image.open(self._gecici_gorsel)).strip().replace(" ", "")
        except Exception as hata:
            # print(f"Hata: {hata}")  # Hata detayını görmek istersen aç
            return None

        return captcha_harfleri

    def karar_ver(self):
        captcha = self.__captcha_ver()
        if not captcha:
            return "Muhtemelen Sisteminizde 'tesseract-ocr' Yüklü Değil!"

        karar_sayfasi = self.oturum.post(
            url=self.sorgu_sayfasi,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Host": "internet2.btk.gov.tr",
                "Origin": self.ana_sayfa,
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

        secici = Selector(karar_sayfasi.text)
        hatali_kod = secici.xpath("//div[@class='icerik']/ul/li/text()").get()
        erisim_var = secici.xpath("//div[@class='yazi2']/text()").get()
        erisim_yok = secici.xpath("//span[@class='yazi2_2']/text()").get()

        return hatali_kod or erisim_var or erisim_yok or ""

    def __repr__(self) -> str:
        hatalar = [
            "Lütfen güvenlik kodunu giriniz.",
            "Güvenlik kodunu yanlış girdiniz. Lütfen Güvenlik Kodunu resimde gördüğünüz şekilde giriniz."
        ]
        max_deneme = 5
        deneme_sayisi = 0

        while deneme_sayisi < max_deneme:
            karar = self.karar_ver()
            if karar not in hatalar:
                try:
                    remove(self._gecici_gorsel)
                except Exception:
                    pass
                return karar
            deneme_sayisi += 1

        try:
            remove(self._gecici_gorsel)
        except Exception:
            pass

        return "⚠️ Maksimum deneme sayısına ulaşıldı, captcha okunamadı."

    def __str__(self):
        return self.__repr__()
