# Reposição BD Insulina

Banco de dados e script de povoamento com canetas de insulina vendidas pela
Pague Menos, para uso no TCC do Insulinet. Guarda nome, fabricante, preço e
descrição de cada caneta.

## Stack

- Python 3.12, SQLAlchemy 2 e Alembic
- PostgreSQL (via Docker Compose)

## Como rodar

1. Suba o Postgres:

   ```
   docker compose up -d
   ```

   Sobe em `localhost:5434`, banco `reposicao_insulina` (ver `docker-compose.yml`).
2. Copie `.env.example` para `.env` (os valores padrão já batem com o
   `docker-compose.yml`).
3. Instale as dependências:

   ```
   python -m venv .venv
   .venv/Scripts/pip install -r requirements.txt   # Linux/Mac: .venv/bin/pip
   ```

4. Rode as migrations:

   ```
   .venv/Scripts/python -m alembic upgrade head
   ```

5. Povoe o banco:

   ```
   .venv/Scripts/python -m scripts.populate_canetas_pague_menos
   ```

   O script busca ao vivo na API pública da Pague Menos. Se a API estiver
   fora do ar, use o snapshot salvo no repositório:

   ```
   .venv/Scripts/python -m scripts.populate_canetas_pague_menos --fonte arquivo
   ```

   Rodar o script de novo apenas atualiza os registros existentes (upsert por
   `fonte_url`), não duplica linhas.

## Estrutura

- `app/models.py` — modelo `CanetaInsulina` (nome, fabricante, preco,
  descricao, fonte_url).
- `alembic/versions/` — migration que cria a tabela `caneta_insulina`.
- `scripts/populate_canetas_pague_menos.py` — busca as canetas na API da
  Pague Menos (categoria Insulina + busca textual, filtrando por
  apresentação em caneta/refil) e grava no banco.
- `data/canetas_pague_menos.json` — snapshot dos dados coletados, usado como
  fallback do script.

A investigação dos endpoints da Pague Menos usados aqui está documentada no
repositório `test-pague-menos-api` do mesmo TCC.
