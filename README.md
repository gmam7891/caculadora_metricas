# Valuator App (Influenciador + Twitch)

Este projeto é um MVP local (Streamlit) para:
- **Influenciador (manual):** CPM, CPC, CPA(FTD), ROI/ROAS e FTD (projetado ou real).
- **Twitch (projeções):** avg viewers / peak (30d) calculados a partir de amostras coletadas via Twitch API, e VOD summary via Twitch API (view_count/duration).

## 1) Pré-requisitos
- Python 3.10+ recomendado
- VS Code (opcional)

## 2) Setup
Crie um ambiente virtual e instale dependências:

```bash
python -m venv .venv
source .venv/bin/activate   # mac/linux
# .venv\Scripts\activate   # windows
pip install -r requirements.txt
```

## 3) Configure credenciais
Copie `.env.example` para `.env` e preencha:

```bash
TWITCH_CLIENT_ID=...
TWITCH_CLIENT_SECRET=...
APP_DB_PATH=./data/app.db
```

> Observação: sem credenciais, o app ainda abre, mas não consegue puxar VODs/ status LIVE via API.

## 4) Rode o coletor (Terminal A)
O coletor salva amostras de `viewer_count` (apenas quando o canal está ao vivo), para você ter **avg viewers e peak** da janela de 30 dias.

```bash
python src/collector.py --channels-file streamers.txt --interval 120
```

- `--interval 120` = coleta a cada 2 minutos (bom custo/benefício).
- Quanto mais tempo rodar, mais confiável fica o avg/peak.

## 5) Rode o app (Terminal B)
```bash
streamlit run app.py
```

## 6) VS Code
Se quiser usar os atalhos de debug, existe um `.vscode/launch.json`.
