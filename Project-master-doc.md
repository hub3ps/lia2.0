# 📋 LIA AGENT v2.0 - DOCUMENTO MESTRE DO PROJETO

> **Última atualização:** 2026-02-04
> **Status:** 🟡 Em Desenvolvimento (Fase 1)
> **Versão:** 2.0.0-alpha

---

## 📑 ÍNDICE

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Stack Tecnológico](#3-stack-tecnológico)
4. [Plano de Implementação](#4-plano-de-implementação)
5. [Checklist de Execução](#5-checklist-de-execução)
6. [Histórico de Mudanças](#6-histórico-de-mudanças)
7. [Decisões Técnicas](#7-decisões-técnicas)
8. [Problemas Conhecidos](#8-problemas-conhecidos)
9. [Como Rodar o Projeto](#9-como-rodar-o-projeto)
10. [Referências](#10-referências)

---

## 1. VISÃO GERAL

### 1.1 O que é o Lia Agent?

Lia é um **agente de IA para pedidos de delivery via WhatsApp**. O cliente envia mensagens de texto/áudio, o agente interpreta o pedido, coleta informações necessárias (endereço, pagamento) e envia o pedido para o sistema PDV (Saipos).

### 1.2 Objetivos da v2.0

| Objetivo                 | Descrição                                      |
| ------------------------ | ---------------------------------------------- |
| **Eliminar alucinações** | Validação Pydantic + Self-correction loops     |
| **Reduzir custos LLM**   | Guardrails filtram ~80% das mensagens simples  |
| **Controle de fluxo**    | FSM explícita (não mais implícita no prompt)   |
| **Multi-tenant**         | Arquitetura pronta para múltiplos restaurantes |
| **Observabilidade**      | Métricas, logs estruturados, auditoria         |

### 1.3 Stakeholders

- **Cliente final:** Marcio Lanches & Pizzas (Itajaí/SC)
- **Desenvolvedor:** Guilherme (Hub3ps)
- **Volume esperado:** 50-100 conversas/dia inicialmente

### 1.4 Integrações

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  WhatsApp   │────▶│  Evolution  │────▶│  Lia Agent  │
│  (Cliente)  │◀────│    API      │◀────│  (FastAPI)  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
                    ▼                          ▼                          ▼
             ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
             │   Saipos    │           │   OpenAI    │           │  Supabase   │
             │    (PDV)    │           │  (GPT-4o)   │           │ (PostgreSQL)│
             └─────────────┘           └─────────────┘           └─────────────┘
```

---

## 2. ARQUITETURA

### 2.1 Fluxo de Mensagens

```
WhatsApp → Evolution API → Webhook (/webhooks/evolution)
                                    │
                                    ▼
                            ┌───────────────┐
                            │ Message Queue │ (Debounce 3s)
                            └───────┬───────┘
                                    │
                                    ▼
                            ┌───────────────┐
                            │  Guardrails   │ (Regex patterns)
                            └───────┬───────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
            ┌───────────────┐               ┌───────────────┐
            │ Quick Intent  │               │  LLM Agent    │
            │ (Sem LLM)     │               │  (OpenAI)     │
            └───────┬───────┘               └───────┬───────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                            ┌───────────────┐
                            │     FSM       │ (Estado da conversa)
                            └───────┬───────┘
                                    │
                                    ▼
                            ┌───────────────┐
                            │    Tools      │ (carrinho, cardápio, etc)
                            └───────┬───────┘
                                    │
                                    ▼
                            ┌───────────────┐
                            │   Resposta    │ → WhatsApp
                            └───────────────┘
```

### 2.2 Máquina de Estados (FSM)

```
GREETING
    │
    ▼
COLLECTING_ITEMS ◀──────────────────────────────┐
    │                                           │
    ├──▶ RESOLVING_PENDING ─────────────────────┤
    │                                           │
    ▼                                           │
CONFIRMING_ITEMS ───────────────────────────────┘
    │
    ▼
COLLECTING_DELIVERY_TYPE
    │
    ├──────────────────────┐
    ▼                      ▼
COLLECTING_ADDRESS    COLLECTING_PAYMENT (pickup)
    │                      │
    ▼                      │
CONFIRMING_ADDRESS         │
    │                      │
    ▼                      │
COLLECTING_PAYMENT ◀───────┘
    │
    ▼
COLLECTING_PAYMENT_DETAILS
    │
    ├──▶ AWAITING_PIX_PROOF (se PIX)
    │           │
    ▼           ▼
CONFIRMING_ORDER
    │
    ▼
ORDER_SENT ────▶ [FIM]

CANCELLED ────▶ [FIM] (pode ocorrer em qualquer estado)
```

### 2.3 Estrutura de Diretórios

```
lia2.0/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app
│   ├── config.py                  # Settings (Pydantic)
│   │
│   ├── api/                       # Rotas HTTP
│   │   ├── __init__.py
│   │   ├── webhooks.py            # POST /webhooks/evolution
│   │   └── admin.py               # Endpoints administrativos
│   │
│   ├── core/                      # Componentes fundamentais
│   │   ├── __init__.py
│   │   ├── fsm.py                 # Máquina de estados
│   │   ├── schemas.py             # Modelos Pydantic
│   │   ├── guardrails.py          # Filtros de entrada
│   │   └── exceptions.py          # Exceções customizadas
│   │
│   ├── services/                  # Lógica de negócio
│   │   ├── __init__.py
│   │   ├── agent/                 # Orquestrador do agente
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py    # Loop principal
│   │   │   ├── tools.py           # Definição das tools
│   │   │   ├── prompts.py         # Templates de prompt
│   │   │   └── validator.py       # Self-correction
│   │   │
│   │   ├── interpreter/           # Parser de pedidos
│   │   │   ├── __init__.py
│   │   │   ├── parser.py          # Extração de itens
│   │   │   ├── matcher.py         # Match com cardápio
│   │   │   └── resolver.py        # Resolução de gírias
│   │   │
│   │   ├── integrations/          # APIs externas
│   │   │   ├── __init__.py
│   │   │   ├── evolution.py       # WhatsApp
│   │   │   ├── saipos.py          # PDV
│   │   │   ├── openai_client.py   # LLM
│   │   │   └── google_maps.py     # Geocoding
│   │   │
│   │   ├── cart.py                # Gestão do carrinho
│   │   ├── menu.py                # Busca no cardápio
│   │   ├── delivery.py            # Taxa de entrega
│   │   ├── order.py               # Processamento de pedidos
│   │   └── client.py              # Gestão de clientes
│   │
│   ├── db/                        # Acesso ao banco
│   │   ├── __init__.py            # Cliente Supabase
│   │   └── repositories/          # Repositórios por entidade
│   │
│   └── utils/                     # Utilitários
│       ├── __init__.py
│       ├── phone.py               # Normalização telefone
│       └── text.py                # Fuzzy matching
│
├── docs/
│   └── PROJECT_MASTER_DOC.md      # Este documento
│
├── migrations/
│   └── 001_initial_schema.sql     # Schema do banco
│
├── prompts/
│   ├── agent.md                   # Prompt principal
│   └── followup.md                # Prompt de retomada
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── .env                           # Variáveis de ambiente (não commitado)
├── .env.example                   # Template de variáveis
├── .gitignore
├── pyproject.toml                 # Dependências Python
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 3. STACK TECNOLÓGICO

### 3.1 Backend

| Tecnologia | Versão | Uso                 |
| ---------- | ------ | ------------------- |
| Python     | 3.9+   | Linguagem principal |
| FastAPI    | 0.109+ | Framework web       |
| Pydantic   | 2.5+   | Validação de dados  |
| Uvicorn    | 0.27+  | Servidor ASGI       |
| Structlog  | 24.1+  | Logging estruturado |

### 3.2 Banco de Dados

| Tecnologia | Uso                                      |
| ---------- | ---------------------------------------- |
| Supabase   | Plataforma (PostgreSQL + Auth + Storage) |
| PostgreSQL | Banco de dados principal                 |
| pg_trgm    | Extensão para fuzzy search               |

### 3.3 Integrações Externas

| Serviço            | Uso                                |
| ------------------ | ---------------------------------- |
| OpenAI GPT-4o-mini | Processamento de linguagem natural |
| Evolution API      | Gateway WhatsApp                   |
| Saipos             | Sistema PDV/POS                    |
| Google Maps        | Geocodificação de endereços        |
| OpenAI Whisper     | Transcrição de áudio               |

### 3.4 Infraestrutura

| Serviço   | Uso                        |
| --------- | -------------------------- |
| Easypanel | Orquestração de containers |
| Docker    | Containerização            |

---

## 4. PLANO DE IMPLEMENTAÇÃO

### 4.1 Fase 1: Fundação (MVP) ⬅️ ATUAL

**Objetivo:** Sistema funcional mínimo para testes

| Módulo                | Status       | Descrição                        |
| --------------------- | ------------ | -------------------------------- |
| Setup inicial         | ✅ Concluído | Repositório, Supabase, estrutura |
| Schema do banco       | ✅ Concluído | 11 tabelas, 3 views, functions   |
| Config/Settings       | ✅ Concluído | Pydantic Settings                |
| FSM                   | ✅ Concluído | 13 estados, transições           |
| Schemas Pydantic      | ✅ Concluído | Cart, Order, Payment             |
| Guardrails            | ✅ Concluído | Regex para sim/não/etc           |
| Exceptions            | ✅ Concluído | Hierarquia de erros              |
| Utils                 | ✅ Concluído | phone.py, text.py                |
| Database client       | ✅ Concluído | Supabase wrapper                 |
| FastAPI base          | ✅ Concluído | /health, /ready, /debug          |
| Order Interpreter     | 🔄 Próximo   | Parser + fuzzy matching          |
| Menu Service          | 🔄 Próximo   | Busca no cardápio                |
| Cart Service          | 🔄 Próximo   | Gestão do carrinho               |
| Evolution Integration | 🔄 Próximo   | Enviar/receber mensagens         |
| Webhook Evolution     | 🔄 Próximo   | POST /webhooks/evolution         |
| Agent Orchestrator    | 🔄 Próximo   | Loop principal + tools           |
| OpenAI Integration    | 🔄 Próximo   | Chat completion                  |
| Prompt do agente      | 🔄 Próximo   | prompts/agent.md                 |

### 4.2 Fase 2: Otimização

**Objetivo:** Melhorar qualidade e reduzir custos

| Módulo               | Status      | Descrição               |
| -------------------- | ----------- | ----------------------- |
| Self-correction loop | ⏳ Pendente | Retry com feedback      |
| Knowledge Graph menu | ⏳ Pendente | Validação de adicionais |
| Cache de cardápio    | ⏳ Pendente | Redis ou in-memory      |
| Métricas/Monitoring  | ⏳ Pendente | conversation_metrics    |
| Testes unitários     | ⏳ Pendente | pytest                  |
| Testes E2E           | ⏳ Pendente | Simulação WhatsApp      |

### 4.3 Fase 3: Produção

**Objetivo:** Deploy e multi-tenant

| Módulo               | Status      | Descrição               |
| -------------------- | ----------- | ----------------------- |
| Integração Saipos    | ⏳ Pendente | Envio real de pedidos   |
| Google Maps          | ⏳ Pendente | Validação de endereço   |
| Validação PIX        | ⏳ Pendente | Vision API              |
| Webhook Saipos       | ⏳ Pendente | Status do pedido        |
| Follow-up automático | ⏳ Pendente | Retomada de conversas   |
| Multi-tenant config  | ⏳ Pendente | Prompts por restaurante |
| Deploy Easypanel     | ⏳ Pendente | Produção                |
| Monitoramento        | ⏳ Pendente | Alertas, dashboards     |

---

## 5. CHECKLIST DE EXECUÇÃO

### ✅ 5.1 Setup Inicial (CONCLUÍDO)

- [x] Criar repositório GitHub (hub3ps/lia2.0)
- [x] Criar projeto Supabase
- [x] Rodar migration 001_initial_schema.sql
- [x] Configurar .env com credenciais
- [x] Instalar dependências (pip install .)
- [x] Testar servidor local (python -m app.main)
- [x] Validar conexão Supabase (/ready)
- [x] Validar guardrails (/debug/guardrails?text=sim)

### 🔄 5.2 Fase 1 - Core (EM ANDAMENTO)

- [ ] **Order Interpreter**
  - [x] Criar app/services/interpreter/parser.py
  - [x] Criar app/services/interpreter/matcher.py
  - [x] Criar app/services/interpreter/resolver.py
  - [x] Implementar parser (extração de itens)
- [x] Implementar matcher (match com cardápio)
- [x] Implementar resolver (normalizações)
- [x] Testar com exemplos reais de pedidos

#### Critérios de Teste — Order Interpreter (Testes 1 e 2)

**Escopo**
- Apenas `parser` / `matcher` / `resolver`
- Sem integrações externas
- Endereço e pagamento fora do escopo do Order Interpreter (neste teste)
- `raw_text` preservado
- 100% das linhas devem virar **item** ou **pendência**

**Regras de fallback**
- Quantidade default: `1`
- “careca” = **sem salada** (remover `Adicionais Salada Geral` quando existir no item base)
- “adicional solto” sem item base → **pendência** `ADICIONAL_NAO_ENCONTRADO` com sugestão quando houver item equivalente
- Normalização: “Burger” → “Burguer”; “porção pequena” → `Batata Frita (1/4 Porção)`

**Cardápio de referência (recorte da view `v_menu_search_index`)**
- Produtos: `X Galinha` (23137416), `X GALINHA 1/2` (23153551), `X Galinha no Prato` (23137422)
- Produtos: `X Burguer` (23137502), `X Salada` (23137463), `X Coração` (23137438)
- Produtos: `Batata Frita (1/4 Porção)` (23137573), `Batata Frita (Meia Porção)` (23137583), `Batata Frita (Porção)` (23137448)
- Produtos: `Guarana 2 Litros` (23172036), `Maionese Caseira Sache` (23193793)
- Adicionais (para X Galinha / X Burguer): Bacon, Batata palha, Coração, Milho, Ervilha, Pepino, Salada Geral

**Teste 1 — Pedido real (multi‑linha)**
```
1 X galinha com bacon
1 X galinha careca com batata palha cortado ao meio
2 maionese adicional
2 X galinha careca com bacon e milho
1 X Burger com coração 
1 X galinha sem ervilha e sem pepino
1 porção pequena de bata frita tradicional
1 guaraná 2 l
```
- Itens esperados:
  - X Galinha (23137416) x1 + Bacon (23137416.17895817)
  - X Galinha (23137416) x1 **sem Salada Geral** (23137416.17895814) + Batata palha (23137416.18691238) + obs: “cortado ao meio”
  - X Galinha (23137416) x2 **sem Salada Geral** (23137416.17895814) + Bacon (23137416.17895817) + Milho (23137416.18275887)
  - X Burguer (23137502) x1 + Coração (23137502.18272960)
  - X Galinha (23137416) x1 **sem Ervilha** (23137416.18275888) e **sem Pepino** (23137416.18275891)
  - Batata Frita (1/4 Porção) (23137573) x1
  - Guarana 2 Litros (23172036) x1
- Pendências esperadas:
  - “2 maionese adicional” → `ADICIONAL_NAO_ENCONTRADO` (sugestão: `Maionese Caseira Sache` 23193793)
- Confiança: **< 1.0** (há pendência)

**Teste 2 — Pedido com endereço/pagamento (fora do escopo)**
```
Ola boa noite, eu gostaria de 2 X salada e 1 X coracao para a rua lico amaral 110, pagamento no cartao na entrega, tudo bem?
```
- Itens esperados:
  - X Salada (23137463) x2
  - X Coração (23137438) x1
- Pendências esperadas: nenhuma
- Confiança: alta

#### Critérios de Teste — Order Interpreter (Testes 3 a 12)

**Escopo**
- Mantém as mesmas regras dos Testes 1 e 2 (apenas `parser` / `matcher` / `resolver`)
- Endereço/pagamento fora do escopo
- 100% das linhas devem virar **item** ou **pendência**

**Testes adicionais (variação de linguagem e contexto)**
- **Teste 3:** Pedido com endereço em linhas separadas + “2 x saladas completos” → X Salada x2
- **Teste 4:** Pedido com “sem milho e sem alface” + torrada + coca 2L
- **Teste 5:** Pedido com metadados WhatsApp + torrada + coca
- **Teste 6:** Pedido com “x burg” + coca 2L
- **Teste 7:** Pedido com variação “bia noite” + coca 2lt
- **Teste 8:** Pedido com “xegg” + removals + coca/guaraná lata
- **Teste 9:** Batata frita com bacon/queijo + suco de morango
- **Teste 10:** “2 x frango” + “x mignon grande” + coca 2L
- **Teste 11:** “x galinha” + “x bacon” + coca 600
- **Teste 12:** “x galinha (bem passado) sem ervilha e pepino”

- [ ] **Menu Service**
  - [ ] Criar app/services/menu.py
  - [ ] Implementar busca por fingerprint
  - [ ] Implementar busca fuzzy
  - [ ] Implementar busca de adicionais por produto
  - [ ] Popular cardápio no banco (sync ou manual)

- [ ] **Cart Service**
  - [ ] Criar app/services/cart.py
  - [ ] Implementar add_item, remove_item, clear
  - [ ] Implementar cálculo de totais
  - [ ] Implementar geração de resumo

- [ ] **Evolution Integration**
  - [ ] Criar app/services/integrations/evolution.py
  - [ ] Implementar send_text_message
  - [ ] Implementar send_buttons (se suportado)
  - [ ] Testar envio de mensagem

- [ ] **Webhook Evolution**
  - [ ] Criar app/api/webhooks.py
  - [ ] Implementar POST /webhooks/evolution
  - [ ] Implementar debounce de mensagens
  - [ ] Implementar processamento de áudio (Whisper)
  - [ ] Configurar webhook na Evolution API

- [ ] **Agent Orchestrator**
  - [ ] Criar app/services/agent/orchestrator.py
  - [ ] Criar app/services/agent/tools.py
  - [ ] Criar app/services/agent/prompts.py
  - [ ] Implementar loop principal
  - [ ] Integrar FSM
  - [ ] Integrar tools

- [ ] **OpenAI Integration**
  - [ ] Criar app/services/integrations/openai_client.py
  - [ ] Implementar chat completion
  - [ ] Implementar function calling
  - [ ] Implementar Whisper (transcrição)

- [ ] **Prompt do Agente**
  - [ ] Criar prompts/agent.md
  - [ ] Definir persona
  - [ ] Definir regras por estado FSM
  - [ ] Definir formato de resposta

- [ ] **Teste E2E Básico**
  - [ ] Enviar "oi" pelo WhatsApp
  - [ ] Receber saudação
  - [ ] Fazer pedido simples
  - [ ] Confirmar pedido (sem enviar ao Saipos)

### ⏳ 5.3 Fase 2 - Otimização

- [ ] Self-correction loop
- [ ] Knowledge Graph do menu
- [ ] Cache de cardápio
- [ ] Métricas de conversação
- [ ] Testes unitários (>80% coverage)
- [ ] Testes de integração

### ⏳ 5.4 Fase 3 - Produção

- [ ] Integração Saipos completa
- [ ] Google Maps geocoding
- [ ] Validação de comprovante PIX
- [ ] Webhook de status Saipos
- [ ] Follow-up automático
- [ ] Deploy em produção
- [ ] Monitoramento e alertas
- [ ] Documentação de operação

---

## 6. HISTÓRICO DE MUDANÇAS

### 2026-02-04 - Order Interpreter (implementação inicial)

**Realizadas:**

- Implementado parser (extração de itens/quantidades/adicionais)
- Implementado matcher (fuzzy/fingerprint + pendências)
- Implementado resolver (normalizações e regras “careca”)

**Arquivos alterados:**

- app/services/interpreter/parser.py
- app/services/interpreter/matcher.py
- app/services/interpreter/resolver.py

### 2026-02-04 - Order Interpreter (testes ampliados + ajustes)

**Realizadas:**
- Ajustes no parser para quantidade implícita, quantidade por palavra e limpeza de saudações/metadados
- Ajustes no resolver para normalização de typos em removals
- Ajustes no matcher para desambiguação de “batata frita + bacon/queijo” e “suco de morango”
- Inclusão de testes reais adicionais (Testes 3 a 12) com variações de linguagem/ordem

**Arquivos alterados:**
- app/services/interpreter/parser.py
- app/services/interpreter/resolver.py
- app/services/interpreter/matcher.py
- scripts/test_order_interpreter.py

### 2026-02-04 - Order Interpreter (estrutura inicial)

**Realizadas:**

- Criados arquivos base do Order Interpreter (parser, matcher, resolver)

**Arquivos criados:**

- app/services/interpreter/parser.py
- app/services/interpreter/matcher.py
- app/services/interpreter/resolver.py

### 2025-02-04 - Setup Inicial

**Realizadas:**

- Criado repositório hub3ps/lia2.0
- Criado projeto Supabase com schema completo
- Estrutura base do projeto Python
- Módulos core: FSM, Schemas, Guardrails, Exceptions
- Módulos utils: phone.py, text.py
- Database client (Supabase)
- FastAPI com endpoints de health check
- Correção de sintaxe para Python 3.9 (Optional[] em vez de |)

**Arquivos criados:**

- migrations/001_initial_schema.sql
- app/main.py
- app/config.py
- app/core/fsm.py
- app/core/schemas.py
- app/core/guardrails.py
- app/core/exceptions.py
- app/db/**init**.py
- app/utils/phone.py
- app/utils/text.py
- pyproject.toml
- .env.example
- Dockerfile
- docker-compose.yml
- README.md

**Validações:**

- ✅ Servidor rodando em localhost:8000
- ✅ Conexão Supabase OK
- ✅ Guardrails funcionando

---

## 7. DECISÕES TÉCNICAS

### 7.1 Por que recriar do zero (não refatorar)?

| Aspecto             | Refatorar v1 | Criar v2   |
| ------------------- | ------------ | ---------- |
| Risco de quebrar    | Alto         | Nenhum     |
| Código legado n8n   | Sim          | Não        |
| Multi-tenant nativo | Adaptado     | Nativo     |
| Tempo total         | ~3 semanas   | ~2 semanas |

**Decisão:** Criar v2 do zero.

### 7.2 Por que FSM explícita?

Na v1, o estado era implícito (inferido pelo prompt). Problemas:

- LLM "esquecia" o estado em conversas longas
- Transições inválidas ocorriam
- Difícil debugar

**Decisão:** FSM explícita em código Python com transições validadas.

### 7.3 Por que Guardrails?

~80% das mensagens são simples ("sim", "ok", "não", números). Chamar LLM para essas é desperdício.

**Decisão:** Classificação por regex primeiro, LLM só quando necessário.

### 7.4 Por que Pydantic para validação?

Na v1, o LLM às vezes retornava `{"quantidade": "dois"}` em vez de `2`. Isso quebrava o código.

**Decisão:** Validação Pydantic com coerção de tipos e self-correction.

### 7.5 Por que não usar LangChain?

- Overhead desnecessário para nosso caso
- Menos controle sobre o fluxo
- Dependência pesada

**Decisão:** Implementação direta com OpenAI SDK + function calling.

---

## 8. PROBLEMAS CONHECIDOS

### 8.1 Resolvidos

| Problema                              | Solução                                                         |
| ------------------------------------- | --------------------------------------------------------------- |
| Python 3.9 não suporta `str \| None`  | Usar `Optional[str]` com `from __future__ import annotations`   |
| pip antigo não suporta pyproject.toml | Atualizar pip antes de instalar                                 |
| Hatch não encontrava pasta app        | Adicionar `[tool.hatch.build.targets.wheel] packages = ["app"]` |

### 8.2 Conhecidos (não críticos)

| Problema               | Impacto                 | Workaround             |
| ---------------------- | ----------------------- | ---------------------- |
| Warning OpenSSL no Mac | Nenhum                  | Ignorar (é só aviso)   |
| Saipos não configurado | Não envia pedidos reais | Usar mock até produção |

---

## 9. COMO RODAR O PROJETO

### 9.1 Pré-requisitos

- Python 3.9+
- Git
- Conta Supabase (com schema aplicado)
- Credenciais: OpenAI, Evolution API

### 9.2 Setup Local

```bash
# 1. Clonar repositório
git clone https://github.com/hub3ps/lia2.0.git
cd lia2.0

# 2. Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# .\venv\Scripts\activate  # Windows

# 3. Atualizar pip
pip install --upgrade pip

# 4. Instalar dependências
pip install .

# 5. Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com suas credenciais

# 6. Rodar servidor
python -m app.main
```

### 9.3 Endpoints Disponíveis

| Endpoint                   | Método | Descrição                       |
| -------------------------- | ------ | ------------------------------- |
| `/`                        | GET    | Root (status básico)            |
| `/health`                  | GET    | Health check                    |
| `/ready`                   | GET    | Readiness check (verifica deps) |
| `/debug/fsm`               | GET    | Mostra estrutura da FSM         |
| `/debug/guardrails?text=X` | GET    | Testa classificação de input    |

### 9.4 Variáveis de Ambiente

```env
# Obrigatórias
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
OPENAI_API_KEY=sk-...
EVOLUTION_BASE_URL=https://xxx
EVOLUTION_API_KEY=xxx
EVOLUTION_INSTANCE=Lia

# Opcionais
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
DEFAULT_TENANT=marcio-lanches

# Saipos (apenas em produção)
SAIPOS_PARTNER_ID=
SAIPOS_PARTNER_SECRET=
SAIPOS_COD_STORE=
SAIPOS_DISPLAY_ID=

# Google Maps (opcional)
GOOGLE_MAPS_API_KEY=
```

---

## 10. REFERÊNCIAS

### 10.1 Documentação Externa

- [FastAPI](https://fastapi.tiangolo.com/)
- [Pydantic](https://docs.pydantic.dev/)
- [Supabase Python](https://supabase.com/docs/reference/python/introduction)
- [OpenAI API](https://platform.openai.com/docs/api-reference)
- [Evolution API](https://doc.evolution-api.com/)

### 10.2 Arquivos de Referência

- **Pesquisa Enterprise:** Documento de 13 páginas com casos Uber, iFood, DoorDash, McDonald's
- **Schema atual:** migrations/001_initial_schema.sql
- **Conversa de planejamento:** Disponível no histórico Claude

### 10.3 Contatos

- **Repositório:** https://github.com/hub3ps/lia2.0
- **Supabase:** [Painel do projeto]

---

## 📌 NOTAS IMPORTANTES

1. **Sempre atualizar este documento** após concluir tarefas ou tomar decisões importantes

2. **Banco de dados:** O schema está em `migrations/001_initial_schema.sql`. Novas alterações devem criar novos arquivos de migration (002_xxx.sql, etc)

3. **Credenciais Saipos:** Serão adicionadas apenas quando o projeto for para produção real

4. **Testes:** Sempre testar localmente antes de fazer deploy

5. **Backup:** Este documento + código no GitHub são o backup completo do projeto

---

_Fim do Documento Mestre - Lia Agent v2.0_
