# certificates

Bu dizin OCR, layout ve LLM servislerine guvenli baglanti icin sertifika dosyalarini barindirir.

Dosyalar buraya eklenir ve `backend/.env` icindeki su degiskenlerle baglanir:

- TLS_CA_CERT_PATH=app/certificates/ca.pem
- TLS_CLIENT_CERT_PATH=app/certificates/client.crt
- TLS_CLIENT_KEY_PATH=app/certificates/client.key

Sertifika eklemek icin kod degisikligi gerekmez. Yalnizca dosyalari bu dizine koyun ve `.env` yollarini guncelleyin. `.env` ve sertifika dosyalari `.gitignore` ile commit disi tutulur.
