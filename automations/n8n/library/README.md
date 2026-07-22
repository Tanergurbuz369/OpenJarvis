# n8n Workflow Library — Category Data

Bu klasör, n8n şablon kütüphanesinden indirilen kategori workflow'larının
tam (içe aktarılabilir) JSON dosyalarını barındırır. **Kod ve araçlar ayrı bir
PR'dadır** (`openjarvis.automations.n8n` + `jarvis n8n` CLI); bu PR yalnızca
veri ekler.

- Her dosya `<id>-<slug>.workflow.json` biçimindedir ve orijinal yazarının
  atfını `meta.owner` alanında korur.
- Tüm dosyalar, commit öncesi sağlayıcı sır kalıpları (Twilio, AWS, Google,
  Slack/Discord webhook, Sendinblue, Stripe, Shopify, Telegram, private key,
  JWT vb.) için tarandı; gömülü kimlik bilgisi taşıyanlar dahil edilmedi.
- Kurmak için (kod PR'ı merge edildikten sonra): `jarvis n8n install`.

Kategoriler ve adetleri için kod PR'ındaki `automations/n8n/README.md` dosyasına
bakın.
