# Güvenlik Kuralları — Tüm AI Agent'lar İçin Zorunlu

Bu depoda üretilen her uygulama, **"Güvenlik Öncelikli Vibe Coding Kuralları"**na (Yasin Arsal, DOA Topluluğu) uymak **zorundadır** — istisnasız.

Hangi agent olursanız olun (Cursor, GitHub Copilot, Codex, Claude vb.) kod üretmeden önce **`CLAUDE.md`** dosyasındaki kuralların tam metnini oku ve uygula.

## Zorunlu kontrol listesi
1. Secret'lar yalnızca `.env`'de; frontend'de ham key yok
2. Her endpoint'te rate limiting (`429` + `Retry-After`)
3. Sunucu tarafı input validation (zod/pydantic), parametreli sorgu
4. Auth: düz metin parola yok (bcrypt/argon2), JWT iyi pratikleri, AuthN + AuthZ
5. SQL: ORM/parametreli sorgu; string birleştirme yok
6. CORS: production'da wildcard `*` yok
7. HTTP güvenlik header'ları (helmet / CSP / HSTS)
8. Dosya yükleme: MIME + boyut doğrulama, UUID ile yeniden adlandırma
9. Hata yönetimi: istemciye stack trace yok, yapısal loglama
10. Bağımlılık: `npm audit`, sabitlenmiş versiyonlar
11. XSS: `dangerouslySetInnerHTML` / `eval()` yok
12. Deploy kontrol listesi
13. AI/LLM: prompt injection önleme, `max_tokens`, sunucu tarafı API key, token bütçeleri

> Tam metin ve kod örnekleri için: [`CLAUDE.md`](./CLAUDE.md)
