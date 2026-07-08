# Goat Fable — Hızlı Kurulum (TR)

[Goat Fable](https://github.com/goatstarter/goat-fable) (MIT lisanslı), Claude Code
oturumlarına çalışma disiplini kuralları ekleyen bir davranış paketidir. Bu dizin,
paketin depoya gömülü (vendored) bir kopyasıdır; içeriği kurulmadan önce satır satır
denetlenmiştir (ağ erişimi ve tehlikeli komut içermez).

## Kurulum (kendi bilgisayarında, tek komut)

Proje kökünde, Git Bash veya terminalde:

```bash
./tools/goat-fable/install.sh .
```

Script şunları yapar:

- `core/`, `guides/`, `hooks/` → `.claude/goat-fable/` altına kopyalar
- 4 skill (`plan-first`, `deep-debug`, `self-review`, `verify-done`) → `.claude/skills/`
- 2 agent (`verifier`, `code-reviewer`) → `.claude/agents/`
- Proje `CLAUDE.md` dosyasına tek satırlık import ekler (bir kez; tekrar çalıştırmak güvenlidir)

`.claude/` dizini bu projede `.gitignore`'da olduğundan kurulum kişiseldir,
commit'lenmez — bu yüzden paket `tools/` altında taşınıyor.

## İsteğe bağlı: stop-verify hook

Kod değişmişken hiç test/build koşulmadıysa oturum sonunda bir kez uyarı verir.
Etkinleştirmek için `.claude/goat-fable/hooks/settings.example.json` içindeki
`"hooks"` anahtarını kendi `.claude/settings.json` dosyana ekle
(ayrıntı: `.claude/goat-fable/hooks/README.md`).

Not: `settings.example.json` model olarak `claude-opus-4-8` önerir; model seçimi
sana kalmış — sadece hook'u almak için yalnızca `"hooks"` anahtarını kopyala.

## Kaldırma

`.claude/goat-fable/`, dört skill dizini, iki agent dosyası ve `CLAUDE.md`'deki
import satırını sil.
