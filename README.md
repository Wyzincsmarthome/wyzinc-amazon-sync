# Wyzinc Amazon Sync

Sincronização automática de produtos entre fornecedores (Visiotech, Suprides) e Amazon Marketplace ES.

## 🚀 Features

- ✅ **Pricing engine corrigido**: Margem aplicada antes dos portes
- ✅ **Matching melhorado**: EAN + Part Number + Keywords
- ✅ **Suprides API**: Classificação automática com job assíncrono
- ✅ **Amazon SP-API**: Feeds de Product, Inventory e Pricing
- ✅ **Storage flexível**: Local ou S3
- ✅ **Deploy automático**: GitHub Actions + Render

## 📋 Requisitos

- Python 3.11+
- Credenciais Amazon SP-API (LWA + AWS)
- Credenciais Suprides API

## 🔧 Setup Local (Opcional)

```bash
# Clone
git clone https://github.com/SEU_USERNAME/wyzinc-amazon-sync.git
cd wyzinc-amazon-sync

# Virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Dependências
pip install -r requirements.txt

# Configuração
cp .env.example .env
# Edita .env com as tuas credenciais

# Teste
python app.py
# Acede: http://localhost:5000/health
```

## 🌐 Deploy no Render

1. **Fork/push** este repo para o teu GitHub
2. **Conecta** o repo ao Render (usa `render.yaml`)
3. **Adiciona** variáveis de ambiente no dashboard:
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
   - `LWA_CLIENT_ID`, `LWA_CLIENT_SECRET`, `LWA_REFRESH_TOKEN`
   - `SELLER_ID`, `MARKETPLACE_ID`
   - `SUPRIDES_BEARER`, `SUPRIDES_USER`, `SUPRIDES_PASSWORD`
4. **Deploy** automático a cada push

## 🧪 Testes

GitHub Actions corre testes automaticamente:
- ✅ Pricing engine (3 cenários)
- ✅ Settings loading
- ✅ Rules validation

Vê o status: [![Tests](https://github.com/SEU_USERNAME/wyzinc-amazon-sync/actions/workflows/test.yml/badge.svg)](https://github.com/SEU_USERNAME/wyzinc-amazon-sync/actions)

## 📊 Endpoints (em desenvolvimento)

- `GET /` - Health check
- `GET /health` - Detailed diagnostics
- `GET /test/pricing` - Test pricing scenarios
- `POST /api/visiotech/upload` - Upload CSV (próximo)
- `POST /api/suprides/classify` - Classify products (próximo)

## 🔒 Segurança

- ❌ **Nunca** commits `.env` (está no `.gitignore`)
- ✅ Usa **secrets** do Render para credenciais
- ✅ `SIMULATE_MODE=true` por padrão (evita chamadas reais)

## 📈 Roadmap

- [ ] Matching por EAN + Part Number
- [ ] Cliente Suprides completo
- [ ] Feeds Amazon (Product, Inventory, Pricing)
- [ ] UI para gestão de produtos
- [ ] Cron job para sincronização diária
- [ ] Logs estruturados (JSON)

## 📄 Licença

Privado - Uso interno Wyzinc
