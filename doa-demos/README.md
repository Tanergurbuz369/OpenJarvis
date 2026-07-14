# DOA Demos — kursun öğrettiği sistemlerin çalışan örnekleri

Bu klasör, "DOA: Fikirden Satışa" programının anlattığı sistem tiplerinin
**sıfırdan yazılmış, çalışan** örneklerini içerir. DOA'nın telifli ders
içeriği/videoları **kopyalanmamıştır**; bunlar temaları örnek alan bağımsız,
açık kaynak demolardır.

## `lead-scraper/` — Lead Scraper & Enrichment

Kursun "müşteri çıkar → zenginleştir → skorla" temasının bağımsız bir örneği.
Bağımlılıksız (saf Node) bir sunucu: bir public dizin API'sinden kişi kayıtları
çeker, her lead'i zenginleştirir (şirket, ünvan, departman, konum, erişim) ve
bir "uygunluk skoru" hesaplayıp panoda gösterir. API anahtarı gerekmez; giden
istekler `HTTPS_PROXY`'yi kullanır.

```bash
cd doa-demos/lead-scraper
npm install                 # yalnızca https-proxy-agent
PORT=4000 node server.js
# tarayıcıda: http://localhost:4000
```

- `GET /api/leads?q=<arama>&limit=<n>` → `{ query, count, leads[] }`
- Skor = erişim (log) + kıdem sinyali (ünvan) + şirket varlığı.

## Ortam araçları (Adım 2'de kuruldu)

Kursun öğrettiği açık kaynak araçlar bu ortama resmî kaynağından kuruldu:

- **n8n 2.29** — `npm i -g n8n` ile kuruldu, `http://localhost:5678` üzerinde
  editörüyle çalışır durumda.
- **Claude Code** — bu oturumun kendisi (zaten kurulu ve aktif).

> Not: Bu demolar geçici ortamda çalışır; kalıcı olması için commit'lenip
> yeniden kurulmaları gerekir. n8n verisi `~/.n8n-demo` altında tutulur.
