# Lia Agent v2.0

> AI Delivery Agent for WhatsApp - Agente de IA para pedidos via WhatsApp

## 🚀 Visão Geral

Lia é um agente de IA que processa pedidos de delivery via WhatsApp, integrando com:
- **Evolution API** - Gateway WhatsApp
- **Saipos** - Sistema PDV
- **OpenAI** - Processamento de linguagem natural
- **Google Maps** - Geocodificação de endereços
- **Supabase** - Banco de dados PostgreSQL

## 📋 Pré-requisitos

- Python 3.11+
- PostgreSQL (Supabase)
- Conta OpenAI
- Evolution API configurada
- (Opcional) Conta Saipos

## 🛠️ Setup

### 1. Clone o repositório

```bash
git clone https://github.com/hub3ps/lia2.0.git
cd lia2.0
```

### 2. Crie o ambiente virtual

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
.\venv\Scripts\activate  # Windows
```

### 3. Instale as dependências

```bash
pip install -e ".[dev]"
```

### 4. Configure as variáveis de ambiente

```bash
cp .env.example .env
# Edite o arquivo .env com suas configurações
```

### 5. Execute a migração do banco

No **Supabase SQL Editor**, execute o conteúdo de:
```
migrations/001_initial_schema.sql
```

### 6. Inicie o servidor

```bash
# Desenvolvimento (com hot reload)
python -m app.main

# Ou com uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 📁 Estrutura do Projeto

```
lia2.0/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configurações centralizadas
│   │
│   ├── api/                    # Rotas da API
│   │   ├── webhooks.py         # Webhooks Evolution/Saipos
│   │   ├── health.py           # Health checks
│   │   └── admin.py            # Endpoints administrativos
│   │
│   ├── core/                   # Componentes fundamentais
│   │   ├── fsm.py              # Máquina de estados
│   │   ├── schemas.py          # Modelos Pydantic
│   │   ├── guardrails.py       # Filtros de entrada
│   │   └── exceptions.py       # Exceções customizadas
│   │
│   ├── services/               # Lógica de negócio
│   │   ├── agent/              # Orquestrador LLM
│   │   ├── interpreter/        # Parser de pedidos
│   │   └── integrations/       # APIs externas
│   │
│   ├── db/                     # Acesso ao banco
│   │   └── __init__.py         # Cliente Supabase
│   │
│   └── utils/                  # Utilitários
│       ├── phone.py            # Manipulação de telefone
│       └── text.py             # Manipulação de texto
│
├── migrations/                 # Scripts SQL
│   └── 001_initial_schema.sql
│
├── prompts/                    # Templates de prompts
│   └── agent.md
│
├── tests/                      # Testes
│
├── .env.example
├── pyproject.toml
└── README.md
```

## 🔧 Arquitetura

### Fluxo de Mensagens

```
WhatsApp → Evolution API → Webhook → Message Queue
                                          ↓
                                    Debounce (3s)
                                          ↓
                                    Input Guardrails
                                          ↓
                              ┌──────────────────────┐
                              │  Classificação       │
                              │  (Regex/Patterns)    │
                              └──────────────────────┘
                                    ↓         ↓
                            [Simples]    [Complexo]
                                ↓              ↓
                        Resposta         LLM Agent
                        Direta          (OpenAI)
                                              ↓
                                    FSM + Tool Calls
                                              ↓
                                    Validação Pydantic
                                              ↓
                                    Resposta → WhatsApp
```

### Máquina de Estados (FSM)

```
GREETING → COLLECTING_ITEMS → CONFIRMING_ITEMS
                ↓                    ↓
         RESOLVING_PENDING    COLLECTING_DELIVERY_TYPE
                                     ↓
                        ┌────────────┴────────────┐
                        ↓                         ↓
               COLLECTING_ADDRESS          COLLECTING_PAYMENT
                        ↓                         ↓
               CONFIRMING_ADDRESS         COLLECTING_PAYMENT_DETAILS
                        ↓                         ↓
                        └────────────┬────────────┘
                                     ↓
                             CONFIRMING_ORDER
                                     ↓
                               ORDER_SENT
```

## 🧪 Testes

```bash
# Roda todos os testes
pytest

# Com coverage
pytest --cov=app

# Testes específicos
pytest tests/unit/test_fsm.py -v
```

## 📚 Endpoints

### Health Checks

- `GET /` - Root
- `GET /health` - Health check básico
- `GET /ready` - Readiness check (verifica dependências)

### Webhooks

- `POST /webhooks/evolution` - Recebe mensagens do WhatsApp
- `POST /webhooks/saipos` - Recebe eventos do Saipos

### Debug (apenas em desenvolvimento)

- `GET /debug/fsm` - Mostra estrutura da FSM
- `GET /debug/guardrails?text=sim` - Testa classificação de input

## 🔐 Variáveis de Ambiente

| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `SUPABASE_URL` | URL do projeto Supabase | ✅ |
| `SUPABASE_KEY` | Service role key | ✅ |
| `OPENAI_API_KEY` | API key OpenAI | ✅ |
| `EVOLUTION_BASE_URL` | URL da Evolution API | ✅ |
| `EVOLUTION_API_KEY` | API key Evolution | ✅ |
| `EVOLUTION_INSTANCE` | Nome da instância | ✅ |
| `GOOGLE_MAPS_API_KEY` | API key Google Maps | ❌ |
| `SAIPOS_*` | Configurações Saipos | ❌ |

## 📝 Próximos Passos

### Fase 1 - Fundação (Atual)
- [x] Schema do banco de dados
- [x] Estrutura base do projeto
- [x] Schemas Pydantic
- [x] Máquina de estados (FSM)
- [x] Input Guardrails
- [ ] Order Interpreter (parser de pedidos)
- [ ] Orquestrador do agente
- [ ] Integração Evolution
- [ ] Webhook de mensagens

### Fase 2 - Otimização
- [ ] Knowledge Graph do menu
- [ ] Sistema de cache
- [ ] Monitoramento e métricas
- [ ] Self-correction loop

### Fase 3 - Multi-tenant
- [ ] Configuração por tenant
- [ ] Prompts customizáveis
- [ ] Dashboard administrativo

## 🤝 Contribuição

1. Fork o repositório
2. Crie sua branch (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -m 'Adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

## 📄 Licença

MIT License - veja [LICENSE](LICENSE) para detalhes.
