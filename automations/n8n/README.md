# n8n Otomasyonları

Bu klasör, OpenJarvis ile birlikte kullanılabilen içe aktarılabilir (importable)
[n8n](https://n8n.io) iş akışlarını (workflow) barındırır. Her `*.workflow.json`
dosyası doğrudan n8n arayüzüne aktarılabilir.

> Kaynak: [digitalacademy.com.tr/n8n-workflows](https://digitalacademy.com.tr/n8n-workflows)
> workflow kütüphanesi, n8n'in resmî `api.n8n.io` şablon API'sini kullanır.
> Bu klasördeki iş akışları OpenJarvis projesine uyarlanmış hazır otomasyonlardır.

## İçindekiler

- [Kütüphane senkronizasyonu + otomatik kurulum](#kütüphane-senkronizasyonu--otomatik-kurulum)
  — 10.700+ n8n şablonunu tarayıp OpenJarvis'e otomatik tanıtan sistem.
- [El ile hazırlanmış iş akışları](#i̇ş-akışları) — `daily_ai_briefing`.

---

## Kütüphane senkronizasyonu + otomatik kurulum

`openjarvis.automations.n8n` modülü, n8n şablon kütüphanesinin tamamını
(`api.n8n.io`, 10.700+ workflow) tarar, hafif bir katalog indeksinde tutar,
tam workflow JSON'unu istenince indirir ve kütüphaneye eklenen **her yeni
workflow'u otomatik olarak** bir OpenJarvis managed-agent template'ine çevirir.
Böylece ajanlar yeni eklenen otomasyonları kendiliğinden tanır.

### Klasör düzeni

```
automations/n8n/
  catalog.json          # her workflow için hafif indeks (id, ad, kategori, node, link)
  library/              # tam, içe aktarılabilir workflow JSON (istenince indirilir)
    <id>-<slug>.workflow.json
  install_manifest.json # hangi workflow'un kurulduğunu izleyen manifest (otomatik)
```

> `catalog.json` kütüphanenin **tamamını** (10.700+ workflow, hafif metadata)
> indeksler ve depoya işlenir. `library/` seçili kategorilerin tam JSON'unu
> içerir (aşağıya bakın). Tüm kütüphanenin tam JSON aynası (`download --all`) ve
> üretilen agent template'leri yerel makinede tutulur, on binlerce dosya depoya
> gönderilmez.

### `library/` — örnekler + kategori veri paketi

Bu PR (kod + araçlar) `library/` altında yalnızca **birkaç örnek** workflow
taşır (test ve gösterim için). ~3.250 workflow'luk **tam kategori koleksiyonu**
(WhatsApp, Airtable, Notion, Telegram, Slack, Google Sheets/Calendar/Drive,
Gmail, Outlook, Discord, OpenAI, HubSpot, Shopify, Stripe, Trello, YouTube,
Twitter/X, WooCommerce, e-ticaret) ayrı bir **veri PR'ında** (`claude/n8n-workflow-library`)
tutulur — böylece kod incelemesi büyük veri diff'iyle karışmaz.

Her iki kaynakta da her dosya orijinal yazarının atfını `meta.owner` alanında
korur ve commit öncesi sağlayıcı sır kalıpları için taranmıştır; gömülü kimlik
bilgisi taşıyanlar dahil edilmemiştir.

Kategori verisini kurmadan da 10.760 workflow'un tamamı **katalogdan** doğrudan
kurulabilir:

```bash
jarvis n8n install --from-catalog     # her workflow için (metadata) agent template
jarvis n8n download --id <id>         # tam JSON gerektiğinde, kaynağından
```

> **Güvenlik:** İçe aktarılan bazı topluluk workflow'ları, yazarları tarafından
> gömülmüş gerçek kimlik bilgileri (ör. Twilio SID, özel anahtar) içerebiliyordu;
> bu dosyalar sızıntıyı önlemek için hariç tutuldu. Kendi indirmelerinde
> (`download --all`) bunları kullanmadan önce kimlik bilgilerini gözden geçir.

### CLI komutları

```bash
# 1) Kataloğu senkronize et (tüm sayfalar). Sınırlamak için --max-pages kullan.
jarvis n8n sync                     # tüm kütüphaneyi indeksle
jarvis n8n sync --max-pages 3       # yalnızca ilk 3 sayfa (hızlı deneme)

# 2) Katalogda ara / listele
jarvis n8n list --limit 25
jarvis n8n list --search whatsapp

# 3) Tam workflow JSON'unu indir
jarvis n8n download --id 2465       # tek workflow
jarvis n8n download --limit 20      # en popüler 20 workflow
jarvis n8n download --all           # her şey (büyük!)

# 4) Yeni/değişen workflow'ları OpenJarvis agent template'ine kur (idempotent)
jarvis n8n install                  # library/'deki indirilmiş dosyalardan
jarvis n8n install --from-catalog   # katalogdaki TÜM workflow'lardan (metadata)
jarvis n8n install --from-catalog --limit 500   # en popüler 500

# 5) Durum
jarvis n8n status
```

### Tümünü indeksle ve hepsini kur

```bash
jarvis n8n sync                     # 10.700+ workflow'un tamamını indeksle
jarvis n8n install --from-catalog   # her birini bir agent template'ine çevir
```

`install --from-catalog`, tam workflow JSON'unu indirmeden **doğrudan
katalogdan** her workflow için bir template üretir (metadata: ad, sahip, node
sayısı, kategori, n8n.io bağlantısı). Böylece on binlerce workflow'u yüzlerce MB
JSON indirmeden kurabilirsin. Bir workflow'un tam JSON'u gerektiğinde
`jarvis n8n download --id <id>` ile alınır.

> **Not (ölçek):** ~10.700 template `~/.openjarvis/templates` altına yazılır
> (repoya değil). Bu, `AgentManager.list_templates()` çağrısında on binlerce TOML
> dosyasının taranması demektir; ilk listelemeler birkaç saniye sürebilir. Daha
> odaklı bir kurulum için `--limit` veya `--search` ile alt küme seçebilirsin.

### Nasıl "otomatik tanıma" çalışıyor?

1. `sync` + `download` (ya da elle bir `*.workflow.json` bırakma) `library/`
   klasörünü doldurur.
2. `install`, `library/` içindeki her workflow için içerik hash'ine bakar;
   **yeni veya değişmiş** olanları bulur (`jarvis n8n status` → "Pending install").
3. Her yeni workflow için `~/.openjarvis/templates/` altına eşleşen bir `.toml`
   template üretir. `AgentManager.list_templates()` bu klasörü zaten taradığı
   için template anında keşfedilir — ek bir kablolama gerekmez.
4. `install` tekrar çalıştırıldığında değişmeyenler atlanır (idempotent); bir
   workflow güncellenirse template'i yeniden üretilir.

### Scheduler'a bağlama (otomatik/periyodik)

`jarvis n8n schedule`, senkronizasyon + otomatik kurulumu **OpenJarvis
scheduler'ına** kaydeder. Bu görev LLM/agent kullanmaz; scheduler tarafından
doğrudan çalıştırılan yerleşik bir `n8n_sync` işidir (job).

```bash
# Her gün 03:00'te kataloğu senkronize et ve yeni workflow'ları kur (varsayılan)
jarvis n8n schedule

# Özel cron / aralık ve seçenekler
jarvis n8n schedule --cron "0 6 * * 1"        # her pazartesi 06:00
jarvis n8n schedule --interval 86400          # her 24 saatte bir
jarvis n8n schedule --max-pages 5             # her çalışmada ilk 5 sayfa
jarvis n8n schedule --download-limit 20       # en popüler 20 workflow'u da indir
jarvis n8n schedule --no-install              # yalnızca katalog; kurulum yapma

# Scheduler daemon'ını çalıştır (görevlerin tetiklenmesi için gerekli)
jarvis scheduler start

# Kaydı kaldır
jarvis n8n unschedule
```

`schedule` idempotenttir: yeniden çalıştırıldığında mevcut n8n sync görevini
değiştirir (mükerrer görev oluşturmaz). Kaydı `jarvis scheduler list` ile
görebilir, çalışma günlüklerini `jarvis scheduler logs <task_id>` ile
izleyebilirsiniz.

Alternatif olarak sistem cron'una da bağlayabilirsiniz:
`0 3 * * * jarvis n8n sync && jarvis n8n install`.

### Üretilen template ne yapar?

Her template, ilgili n8n otomasyonunu **bilen** bir OpenJarvis orkestratör
ajanı tanımlar: iş akışının tetikleyicisini, node türlerini ve sahibini özetler;
kullanıcıya kurulumda, kimlik bilgisi ayarında ve uyarlamada yardım eder. Gerçek
bir n8n sunucusu gerektirmez; n8n JSON'u `library/` içinde referans olarak durur.

---

## İş Akışları

| Dosya | Ne yapar? | Tetikleyici | Gerekli kimlik |
| --- | --- | --- | --- |
| `daily_ai_briefing.workflow.json` | Her sabah 08:00'de Hacker News'ten en yüksek puanlı yapay zekâ/teknoloji haberlerini toplar, Türkçe bir brifing hazırlar ve Slack'e gönderir. | Schedule (günlük 08:00) | Slack |

**Sahip / Owner:** Mert Durmazer

---

## `daily_ai_briefing.workflow.json` — Günlük Yapay Zeka Brifingi

### Akış şeması

```
Her Sabah 08:00 (Schedule)
      │
      ▼
Haberleri Getir (HTTP Request → Hacker News Algolia API)
      │  ├── başarı ─▶ Brifingi Hazırla (Code)
      │  │                    │
      │  │                    ▼
      │  │              Sonuç Var mı? (IF)
      │  │                ├── evet ─▶ Slack'e Gönder
      │  │                └── hayır ─▶ Bugün Haber Yok (NoOp)
      │  └── hata ─▶ Hata Yakalandı (NoOp)
```

- **Hata yönetimi:** HTTP Request node'u başarısız olursa **3 kez** (2 sn arayla)
  yeniden dener; yine başarısız olursa akış `Hata Yakalandı` dalına düşer
  (`onError: continueErrorOutput`). Bu dala bir Slack/e-posta uyarı node'u
  ekleyerek arıza bildirimi alabilirsiniz.
- **Boş sonuç koruması:** `Sonuç Var mı?` IF node'u, hiç haber gelmediğinde
  Slack'e boş mesaj gönderilmesini engeller.

### Kurulum adımları

1. **İş akışını içe aktarın**
   - n8n arayüzünde sağ üstten **⋯ → Import from File** (veya
     *Workflows → Import*) seçin.
   - `automations/n8n/daily_ai_briefing.workflow.json` dosyasını seçin.

2. **Slack kimlik bilgisini bağlayın**
   - `Slack'e Gönder` node'unu açın.
   - **Credential to connect with → Create New** ile bir Slack kimliği ekleyin
     (OAuth2 veya Bot Token). Bot'un `chat:write` iznine ve hedef kanala erişimi
     olmalı.
   - `Channel` alanına hedef kanalı yazın (örn. `#genel` veya kanal ID'si).

3. **Zamanı ayarlayın (opsiyonel)**
   - `Her Sabah 08:00` node'undan saat/dakikayı değiştirebilirsiniz.

4. **İş akışını etkinleştirin**
   - Sağ üstteki **Active** anahtarını açın. Zamanlanmış tetikleyicinin
     çalışması için iş akışının kaydedilmiş ve aktif olması gerekir.

### Test senaryoları

1. **Manuel çalıştırma (mutlu yol):**
   `Her Sabah 08:00` node'unda **Execute Node** (ya da tuval üstünde
   **Test workflow**) deyin. `Brifingi Hazırla` çıktısında `count = 5` ve
   markdown formatlı `message` görülmeli; Slack kanalına brifing düşmeli.

2. **Boş sonuç:**
   `Haberleri Getir` node'unda `numericFilters` değerini geçici olarak
   `points>1000000` yapın. Akış `Bugün Haber Yok` dalına gitmeli, Slack'e mesaj
   **gönderilmemeli**.

3. **Hata / yeniden deneme:**
   `Haberleri Getir` node'unda `url` değerini geçersiz bir adrese
   (örn. `https://hn.algolia.com/api/v1/yok`) çevirin. Node 3 kez denemeli ve
   akış `Hata Yakalandı` dalına düşmeli.

4. **Slack kimliği eksik:**
   Kimlik bağlamadan çalıştırın; `Slack'e Gönder` node'u kimlik hatası vermeli,
   önceki node'lar başarıyla tamamlanmalı.

### Sorun giderme

- **Slack'e mesaj gitmiyor:** Bot'un kanala eklendiğinden ve `chat:write`
  iznine sahip olduğundan emin olun; özel kanallarda bot'u kanala davet edin.
- **Zamanlayıcı tetiklenmiyor:** İş akışı **Active** değilse zamanlanmış
  tetikleyici çalışmaz. Ayrıca n8n zaman diliminizi (**Settings → Timezone**)
  kontrol edin.
- **HTTP 429 / rate limit:** Hacker News API'si nadiren sınırlar; `Haberleri
  Getir` node'undaki yeniden deneme ayarları çoğu geçici hatayı örter.

### Yerel alternatif (local-first)

OpenJarvis'in yerel-öncelikli felsefesine uygun olarak, aynı işi buluta
bağlanmadan cihaz üzerinde yapan bir yönetilen-ajan (managed-agent) şablonu da
eklenmiştir: `src/openjarvis/agents/templates/daily_ai_briefing.toml`. Bu şablon
`web_search` aracıyla günlük brifingi Türkçe üretir ve OpenJarvis içinden
zamanlanabilir.
