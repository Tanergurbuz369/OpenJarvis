# Jarvis ile Instantly E-mail Kampanyası Kurma

Bu rehber, Jarvis'e [Instantly.ai](https://instantly.ai) üzerinde uçtan uca bir
soğuk e-posta (cold e-mail) kampanyası kurdurmayı anlatır: gönderici hesap
kontrolü, sekans yazımı, kampanya oluşturma, lead ekleme ve yayına alma.

## Ön Koşullar

1. **Instantly hesabı** — [instantly.ai](https://instantly.ai) üzerinde bir
   hesap (kampanya + API erişimi için Hypergrowth veya üzeri plan gerekir).
2. **Bağlı gönderici hesap(lar)** — Instantly panelinde *Email Accounts*
   bölümünden en az bir gönderici e-posta hesabı bağlayın. Soğuk e-posta için
   ana alan adınızı değil, satın alacağınız benzer bir alan adını (ör.
   `acme.co`, `tryacme.com`) kullanmanız ve hesapları 2-3 hafta warm-up'ta
   tutmanız önerilir.
3. **API anahtarı** — Instantly panelinde **Settings → Integrations → API
   Keys** yolundan yeni bir anahtar oluşturun.

API anahtarını Jarvis'in göreceği ortama ekleyin:

```bash
export INSTANTLY_API_KEY="..."
```

Kalıcı olması için `~/.config/openjarvis/.env` veya shell profilinize koyun.

## Hızlı Başlangıç

Hazır ajan şablonunu kullanın:

```bash
jarvis agents create --template instantly_email_campaign \
  --instruction "Hedef: Türkiye'deki butik e-ticaret ajansları. Teklif: aylık sabit ücretle AI otomasyon kurulumu. Ton: samimi ama profesyonel."
```

Ajan sırasıyla şunları yapar:

1. `list_accounts` ile bağlı gönderici hesapları doğrular.
2. Hedef sektörü araştırıp 3 adımlı bir sekans yazar:
   e-posta 1 (giriş) → 2 gün sonra e-posta 2 (farklı açı, aynı thread) →
   3 gün sonra e-posta 3 (kibar kapanış).
3. `create_campaign` ile kampanyayı **duraklatılmış** olarak kurar
   (Europe/Istanbul, hafta içi 09:00–17:00, hesap başına günlük 30 e-posta).
4. Verdiğiniz lead listesini `add_leads` ile ekler ve her lead için
   kişiselleştirme cümlesi yazar.
5. Önizlemeyi gösterir ve **sizin onayınız olmadan kampanyayı
   aktifleştirmez**. "Aktifleştir" dediğinizde `activate_campaign` çağrılır.

## `instantly_campaign` Aracı

Şablon kullanmadan, sohbet içinde de kullanabilirsiniz. Aracın aksiyonları:

| Aksiyon | Gerekli parametreler | Ne yapar |
|---|---|---|
| `list_accounts` | — | Bağlı gönderici hesapları listeler |
| `create_campaign` | `name`, `steps` | Sekanslı kampanya kurar (paused) |
| `add_leads` | `campaign_id`, `leads` | Kampanyaya lead ekler |
| `list_campaigns` | — | Kampanyaları listeler |
| `get_campaign` | `campaign_id` | Kampanya detayını getirir |
| `activate_campaign` | `campaign_id` | Gönderimi başlatır |
| `pause_campaign` | `campaign_id` | Gönderimi durdurur |
| `get_analytics` | `campaign_id` | Açılma/yanıt istatistiklerini getirir |

`create_campaign` için `steps` formatı:

```json
[
  {"subject": "kısa soru", "body": "Merhaba {{firstName}}, ...", "delay": 0},
  {"subject": "", "body": "Tekrar merhaba, ...", "delay": 2},
  {"subject": "", "body": "Son bir not...", "delay": 3}
]
```

- `delay`: bir önceki e-postadan kaç gün sonra gönderileceği.
- `subject` boş bırakılırsa e-posta aynı thread'de devam eder (takip
  e-postalarında önerilen yöntem).
- Kişiselleştirme değişkenleri: `{{firstName}}`, `{{lastName}}`,
  `{{companyName}}`, `{{personalization}}` — değerler lead eklerken dolar.

Varsayılan kampanya ayarları bilinçli olarak temkinlidir:

- `stop_on_reply: true` — yanıt gelen lead'e sekans durur.
- `open_tracking` / `link_tracking` kapalı, `text_only` açık —
  teslim edilebilirlik (deliverability) için düz metin en güvenlisidir.
- `daily_limit: 30` — warm-up dostu hacim; hesaplarınız oturduktan sonra
  yükseltebilirsiniz.

## İyi Pratikler

- **İzinsiz listelere dikkat**: KVKK/GDPR kapsamında hukuki sorumluluk size
  aittir; her e-postaya çıkış (opt-out) cümlesi ekleyin.
- **Kısa yazın**: ilk e-posta 60–90 kelime, tek CTA, tek soru.
- **Spam kelimelerinden kaçının**: "ücretsiz!!", "garanti", "hemen tıkla"
  gibi kalıplar ve linkler spam filtrelerini tetikler.
- **Küçük başlayın**: 1 hesap × 30/gün ile başlayıp yanıt oranını görmeden
  hacmi artırmayın.

## Sorun Giderme

- `INSTANTLY_API_KEY is not set` — anahtarı export ettiğiniz shell'den mi
  başlattınız? `jarvis doctor` ortam değişkenlerini gösterir.
- `401` — anahtar yanlış veya planınız API erişimi içermiyor.
- `add_leads` kısmi hata dönerse sonuçtaki `errors` listesi hangi e-postanın
  neden reddedildiğini gösterir (genellikle geçersiz adres).
- Kampanya kuruldu ama gönderim yok — kampanya paused olarak oluşur;
  `activate_campaign` çağrıldı mı ve gönderim penceresi içinde misiniz?
