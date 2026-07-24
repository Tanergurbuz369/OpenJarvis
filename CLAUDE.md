# Proje Talimatları

## Dil

Bu depoda (OpenJarvis) çalışırken kullanıcıyla olan TÜM iletişim Türkçe olmalıdır:
cevaplar, sorular, açıklamalar, ilerleme güncellemeleri — hepsi Türkçe. Bu kalıcı
bir emirdir, unutma. (Kod, commit mesajları, PR başlıkları/açıklamaları ve teknik
tanımlayıcılar İngilizce kalabilir; sadece kullanıcıya yönelik metin Türkçe olmalı.)

## Skill Keşfi

Kullanıcı bir soru sorduğunda ya da bir proje/fikir/istekle geldiğinde (basit,
tek seferlik bir işlem değilse):

1. **Önce yerel skill'lere bak** — `.claude/skills/**`, `.claude/skills/ecc/**`.
2. **Uygun yoksa açık kayıt defterini tara** — `agentskills.io` standardı,
   88.000+ skill (Hermes Agent'ın `hermes-agent.nousresearch.com/docs/skills`
   adresinde gösterdiği aynı katalog). Tarama için `npx skills find <anahtar
   kelimeler>` — tam süreç için `.claude/skills/skill-discovery/SKILL.md`.
3. **Bulduklarını sun, otomatik kurma** — yerel ve/veya online adayları
   kullanıcıya söyle, kullanıcı hangisini seçerse ("şu skill'i kullanalım")
   ondan devam et.
4. **Kayıt defterinden asla toplu kurulum yapma** — tek tek, incelenerek,
   `.claude/skills/skill-discovery/SKILL.md` ve
   `.claude/rules/ecc/common/security.md`'deki süreçle.

Bu talimat, `AGENTS.md` dosyasındaki araçtan bağımsız (agent-agnostic)
versiyonuyla birebir aynıdır — hangi AI agent kullanılırsa kullanılsın
geçerlidir.
