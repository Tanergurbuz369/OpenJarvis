# Güvenlik Öncelikli Vibe Coding Kuralları

> **Kaynak:** Yasin Arsal — DOA Topluluğu (17 Haziran 2026)
> Bu depoda ve bu depoyu kullanan **her** AI agent (Claude Code, Cursor, GitHub Copilot, Codex vb.) tarafından üretilen her uygulama aşağıdaki kurallara uymak zorundadır — **istisnasız**.

## 🔐 1. Secret'lar & Ortam Değişkenleri
- Tüm API key, token, veritabanı URL'si, servis kimlik bilgisi ve özel config **sadece** `.env` dosyalarında bulunur.
- `.env`, `.env.local`, `.env.*.local` her zaman `.gitignore`'da olmalı.
- Frontend kodu ASLA ham secret içermez (`const API_KEY = "sk-..."` yasak).
- Next.js/Vite'de yalnızca `NEXT_PUBLIC_` / `VITE_` ön ekli değişkenler istemciye açıktır; bunlar ASLA secret olmamalı.
- Sunucu secret'larına `process.env.VAR_NAME` ile erişilir, API yanıtında istemciye dönülmez.
- Tüm değişken adlarını boş değerlerle içeren bir `.env.example` üret.
- İstemcide zorunlu public key (örn. Stripe publishable) varsa kasıtlı olduğunu yorumla belirt.

```js
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY); // ✅
const stripe = require('stripe')('sk_live_abc123...');           // ❌
```

## 🚦 2. Rate Limiting
- Dışarıya açık her endpoint'te rate limiting olmalı (özellikle auth, form, AI completion, dosya yükleme).
- Varsayılan limitler: Auth 15 dk'da 5/IP · Genel API 60/dk/IP · AI/LLM 10/dk/kullanıcı · Yükleme 5/dk/IP.
- Kütüphaneler: Express `express-rate-limit`, Next.js `lru-cache` middleware, FastAPI `slowapi`, Flask `Flask-Limiter`, Edge/Vercel Upstash Redis.
- Limit aşımında `Retry-After` ile `429 Too Many Requests` dön; frontend'de net mesaj göster.

## 🧹 3. Input Validation & Sanitization
- Tüm girdiler **sunucu tarafında** doğrulanır; istemci doğrulaması yalnızca UX içindir.
- Şema doğrulama: JS/TS `zod`/`yup`/`joi`, Python `pydantic`.
- Saklamadan/göstermeden önce string'leri temizle (XSS).
- Parametreli sorgu / ORM kullan; kullanıcı girdisini asla ham sorguya gömme.
- Tip, uzunluk, izinli karakter, zorunlu alan, enum doğrula. Geçersizde `400` dön ve logla.

```ts
import { z } from 'zod';
const schema = z.object({ email: z.string().email().max(254), message: z.string().min(1).max(1000).trim() });
const result = schema.safeParse(req.body);
if (!result.success) return res.status(400).json({ error: result.error });
```

## 🔑 4. Kimlik Doğrulama & Yetkilendirme
- Yerleşik auth kütüphaneleri kullan (NextAuth, Clerk, Supabase Auth, Auth0, Passport, lucia-auth); auth'u sıfırdan yazma.
- Parolalar düz metin saklanmaz: `bcrypt` (min cost 12) veya `argon2`.
- JWT güçlü secret ile imzalanır (`JWT_SECRET` ≥ 32 karakter), kısa expiry (15m–1h).
- Refresh token httpOnly cookie'de (localStorage'da değil).
- Her istekte hem kimlik (AuthN) hem kaynak izni (AuthZ) doğrulanır.
- Başarısız girişlerde hesap kilitleme; admin/hassas işlemlerde rol kontrolü.

## 🛡️ 5. SQL & Veritabanı Güvenliği
- Daima ORM (Prisma, Drizzle, SQLAlchemy, Mongoose) veya parametreli sorgu.
- Sorguyu kullanıcı verisiyle string birleştirme.
- En az ayrıcalık ilkesi; ham DB hatalarını istemciye dönme.

## 🌐 6. CORS
- Production'da wildcard `*` yok; yalnızca izinli origin'leri beyaz listeye al, metotları sınırla.

## 🪝 7. HTTP Güvenlik Header'ları
- `helmet` (Node) / `django-csp` (Django) ile: CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, HSTS, `Referrer-Policy: strict-origin-when-cross-origin`. `X-Powered-By` kaldır.

## 📤 8. Dosya Yükleme Güvenliği
- MIME + uzantı + boyut sunucu tarafında doğrulanır (istemcinin iddiasına güvenme).
- Boyut limitleri (örn. görsel 5MB, doküman 25MB).
- Dosyalar web kökü dışında / cloud bucket'ta saklanır; çalıştırılabilir izinle sunulmaz.
- UUID ile yeniden adlandır; gerekirse malware taraması.

## 🚨 9. Hata Yönetimi & Loglama
- İstemciye stack trace / iç yol dönme; genel mesaj göster ("Bir şeyler ters gitti").
- Sunucu tarafında bağlamla logla (zaman damgası, kullanıcı ID, route, temiz girdi).
- Sentry/Datadog/Logtail kullan; `4xx` ile `5xx` ayır.

## 🔒 10. Bağımlılık Güvenliği
- `npm audit` / `pip-audit` / `cargo audit` çalıştır, high/critical düzelt.
- Bakımsız paketlerden kaçın; versiyonları sabitle (lock dosyaları).

## 🧱 11. XSS Önleme / CSP
- `dangerouslySetInnerHTML` yalnızca `DOMPurify` ile temizlenmiş içerikte.
- Kullanıcı içeriğiyle `eval()` / `new Function()` / `innerHTML` yok; inline `<script>`'ten kaçın.

## ☁️ 12. Deploy Kontrol Listesi
- `.env` commit edilmemiş · secret'lar host config'inde · debug/dev log kapalı · DB herkese açık değil · HTTPS zorunlu · rate limiting aktif · CORS sınırlı · kullanılmayan route'lar kaldırılmış/korunmuş.

## 🤖 AI/LLM Özel Kuralları
- Ham kullanıcı girdisini temizlemeden LLM'e gönderme (prompt injection).
- LLM çağrılarında daima `max_tokens` limiti.
- API key yalnızca sunucuda; tüm LLM çağrıları backend üzerinden, asla tarayıcıdan değil.
- Kullanıcı başına token kullanımını logla; token bütçeleri uygula.
- LLM çıktısını UI'da render etmeden önce doğrula/temizle (XSS riski).
