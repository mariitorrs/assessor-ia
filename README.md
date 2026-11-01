<div align="center">

<img src="docs/assets/capa.png" width="1200" alt="Assessor.ai — finanças e compromissos em uma conversa só. Capa em verde e creme com maçã de tecido, laço xadrez e flores." />

<br />

Aplicação web de assistência financeira e organização de agenda, com agentes especializados,<br />
memória de conversas e verificação de respostas por evidências.

<img src="docs/assets/tecnologias.svg" width="900" alt="Python, FastAPI, LangChain, LangGraph, PostgreSQL, MongoDB e Qdrant" />

<br />

[Sobre](#sobre-o-projeto) &nbsp; · &nbsp; [Funcionalidades](#o-que-o-assessor-faz) &nbsp; · &nbsp; [Arquitetura](#como-funciona) &nbsp; · &nbsp; [Execução](#como-executar) &nbsp; · &nbsp; [Aprendizados](#aprendizados)

</div>

<img src="docs/assets/divisor.svg" width="1200" alt="" />

## Sobre o projeto

O Assessor.ai é um projeto acadêmico desenvolvido no Ensino Médio Técnico da Germinare Tech para explorar a construção de uma aplicação com inteligência artificial conectada a ferramentas e bancos de dados.

A proposta é organizar informações do dia a dia por meio de uma conversa: registrar um gasto, consultar o saldo, encontrar um compromisso ou retomar algo mencionado em outra sessão. Por trás do chat, agentes especializados interpretam os pedidos e utilizam ferramentas para consultar ou registrar informações.

O projeto reúne desenvolvimento web, integração de modelos de linguagem, persistência de dados e busca semântica. Ao longo da implementação, também foram incorporadas camadas de proteção, personalização, monitoramento e avaliação da fidelidade das respostas.

## O que o Assessor faz

### Organização financeira

- Registra receitas, despesas e transferências informadas pelo usuário.
- Consulta transações por texto, tipo e intervalo de datas.
- Atualiza registros financeiros existentes.
- Calcula saldo total e saldo diário a partir dos registros no PostgreSQL.
- Consulta o perfil financeiro para contextualizar orientações.

### Agenda

- Registra compromissos com título, data, horário e informações adicionais.
- Consulta eventos por texto, dia ou intervalo de datas.
- Inclui eventos no Google Calendar quando a integração está configurada e autorizada.
- Trabalha com datas locais no fuso `America/Sao_Paulo`.

### FAQ com busca semântica

O agente de FAQ consulta o documento `FAQ_assessor_v1.1.pdf` por meio de RAG, ou geração aumentada por recuperação. O PDF é dividido em trechos, transformado em embeddings e indexado no Qdrant. Quando chega uma pergunta, a ferramenta recupera trechos relevantes para apoiar a resposta.

### Memória de conversas

O histórico de cada sessão é armazenado no MongoDB. Ao encerrar uma conversa, o sistema gera um resumo e o indexa no Qdrant para permitir a recuperação semântica de informações em sessões futuras.

O estado da conversa em andamento também utiliza o checkpointer em memória do LangGraph. Esse estado temporário e o histórico persistido têm funções diferentes: o primeiro sustenta a execução do grafo; o segundo guarda mensagens e resumos.

### Perfil financeiro

Uma página própria permite cadastrar renda mensal, objetivo, tolerância a risco e preferências. Os dados estruturados ficam no MongoDB, enquanto as preferências são representadas no Qdrant para consulta pelo agente financeiro.

### Monitoramento

Um painel acompanha os turnos e as chamadas dos modelos, incluindo:

- Latência e percentil 95.
- Tokens de entrada e saída.
- Custo estimado a partir dos preços configurados no código.
- Uso de fallback entre modelos.
- Status dos turnos e taxa de erro.

Os registros de monitoramento ficam na memória do processo, com retenção dos últimos 50 turnos. Os custos são estimativas das chamadas instrumentadas, e não uma conciliação da fatura de todos os serviços externos.

## Interface

O frontend foi construído com HTML, CSS e JavaScript, com uma identidade visual inspirada em scrapbook: papéis, adesivos, elementos de maçã, detalhes florais e cores suaves.

A intenção foi dar uma aparência acolhedora a uma ferramenta de organização pessoal. A aplicação possui chat com sugestões de mensagens, identificação da sessão, botão para iniciar uma nova conversa, formulário de perfil e painel de monitoramento.

<img src="docs/assets/divisor.svg" width="1200" alt="" />

## Como funciona

O LangGraph organiza o fluxo entre os agentes e as etapas de verificação.

```mermaid
flowchart TD
    A["Mensagem do usuário"] --> B["Guardrail de entrada"]
    B -->|Bloqueio ou encerramento| Z["Fim do turno"]
    B -->|Pedido permitido| C["Roteador"]
    C --> D["Agente financeiro"]
    C --> E["Agente de agenda"]
    C --> F["Agente de FAQ"]
    C -->|Resposta direta| Z
    D --> G["Orquestrador"]
    E --> G
    G --> H["Guardrail de saída"]
    H --> I["Juiz de evidências"]
    F --> I
    I --> Z
    classDef papel fill:#fffdf2,stroke:#9bb375,color:#35553b
    classDef verde fill:#e7efcf,stroke:#6f974d,color:#35553b
    classDef rosa fill:#f8e8de,stroke:#be5046,color:#983f38
    classDef amarelo fill:#f6edc7,stroke:#d89f3f,color:#695e35
    class A,Z papel
    class C,D,E,F verde
    class B,H,I rosa
    class G amarelo
```

| Componente | Responsabilidade |
| --- | --- |
| Roteador | Identifica o domínio do pedido e encaminha para um especialista. |
| Agente financeiro | Utiliza ferramentas de transações, saldos, memória e perfil. |
| Agente de agenda | Utiliza ferramentas de compromissos, memória e Google Calendar. |
| Agente de FAQ | Consulta os trechos recuperados do PDF. |
| Orquestrador | Organiza a resposta dos especialistas financeiro e de agenda. |
| Guardrails | Aplicam verificações de entrada e revisão de saída nas rotas previstas. |
| Juiz | Compara a resposta com as evidências reunidas no turno. |

### Modelos e fallback

Na configuração do código:

- **Gemini 2.5 Flash:** modelo principal dos especialistas financeiro e de agenda.
- **GPT-OSS 120B via Groq:** roteamento, FAQ, orquestração e outras tarefas auxiliares; também é o fallback dos especialistas.
- **Gemini Embedding:** geração dos vetores usados na busca semântica.
- **JEV via Typesafe:** avaliação final de fidelidade às evidências.

O fallback permite tentar outro provedor quando a chamada principal falha. A execução depende do acesso aos modelos e serviços configurados.

## Dados e persistência

Cada banco atende a uma necessidade da aplicação.

| Tecnologia | Uso no projeto |
| --- | --- |
| PostgreSQL | Transações financeiras, categorias, tipos de transação e eventos. |
| MongoDB | Sessões, mensagens, resumos e dados estruturados do perfil. |
| Qdrant | Busca semântica em resumos, trechos do FAQ e preferências do perfil. |

As coleções vetoriais utilizadas são `memoria_resumos`, `faq_chunks` e `perfil_preferencias`, com vetores de 768 dimensões e similaridade por cosseno.

## Proteção e fidelidade das respostas

O guardrail de entrada aplica mascaramento de padrões de dados pessoais, verificações de tentativas de prompt injection e classificação semântica de pedidos. Nas rotas financeira e de agenda, a saída passa por tratamento de dados pessoais e revisão de conteúdo financeiro.

O juiz tardio verifica a resposta depois da execução do agente, usando a pergunta e as evidências reunidas no turno. A aprovação exige o veredito `apoiada` e pontuação de pelo menos `0.70`. Em caso de reprovação, falta de chave ou falha na avaliação de uma resposta, o sistema utiliza uma mensagem fixa:

> Não tenho evidência para afirmar isso.

Essa avaliação reduz a chance de apresentar afirmações sem apoio, mas não garante ausência de erros. Na implementação documentada, o juiz avalia a resposta; sua rejeição não implica desfazer operações que as ferramentas já tenham confirmado no banco ou em serviços externos.

## Integrações com MCP

O projeto inclui um servidor MCP que expõe ferramentas de finanças e agenda para clientes compatíveis, usando transporte `stdio`.

Também existe um cliente para o MCP do Google Calendar, com fallback para a Calendar API em condições específicas de erro. A criação de eventos exige autorização da conta Google.

<img src="docs/assets/divisor.svg" width="1200" alt="" />

## Tecnologias

| Camada | Tecnologias |
| --- | --- |
| Backend | Python, FastAPI, Uvicorn e Pydantic |
| Agentes e fluxo | LangChain e LangGraph |
| Modelos | Google Gemini e Groq |
| Busca semântica | Qdrant e embeddings do Gemini |
| Persistência | PostgreSQL, psycopg2 e MongoDB |
| Integrações | MCP, Google Calendar e OAuth 2.0 |
| Avaliação | Typesafe / JEV |
| Frontend | HTML, CSS, JavaScript e SVG |
| Configuração | python-dotenv |

## Organização do código

| Caminho | Conteúdo |
| --- | --- |
| `app/main.py` | Inicialização da API e disponibilização do frontend. |
| `app/graph.py` | Estado, nós e fluxo do LangGraph. |
| `app/agents.py` e `app/prompts.py` | Agentes e instruções de cada papel. |
| `app/llms.py` | Modelos e fallback. |
| `app/guardrail.py` | Verificações de entrada e revisão de saída. |
| `app/juiz.py` | Avaliação das respostas por evidências. |
| `app/memory.py` | Histórico, encerramento e resumos das sessões. |
| `app/perfil.py` | Persistência e consulta do perfil financeiro. |
| `app/vectorstore.py` | Cliente Qdrant e geração de embeddings. |
| `app/ingest_faq.py` | Indexação do PDF do FAQ. |
| `app/observabilidade.py` | Coleta de métricas de chamadas e turnos. |
| `app/mcp_server.py` | Exposição das ferramentas via MCP. |
| `app/routes/` | Rotas de chat, perfil, sessões e monitoramento. |
| `app/tools/` | Ferramentas financeiras, agenda, memória, FAQ e calendário. |
| `frontend/` | Interface web e elementos visuais. |
| `data/` | Documento utilizado pelo FAQ. |
| `scripts/verificar_prerequisitos.py` | Verificação de dependências e serviços. |

<img src="docs/assets/divisor.svg" width="1200" alt="" />

## Como executar

### 1. Preparar o ambiente Python

Na raiz do projeto:

```bash
python -m venv .venv
```

Ative o ambiente no Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Ou no Linux e macOS:

```bash
source .venv/bin/activate
```

Instale as dependências:

```bash
python -m pip install -r requirements.txt
```

### 2. Configurar os serviços

É necessário ter acesso ao PostgreSQL, MongoDB e Qdrant, além das APIs utilizadas pelos modelos e pelo juiz.

O PostgreSQL precisa estar preparado com o esquema esperado pelas ferramentas, incluindo `transactions`, `transaction_types`, `categories` e `events`. A versão documentada não inclui um script SQL de criação do banco; instalar as dependências Python não cria essas tabelas.

O cliente principal de MongoDB utiliza TLS. A conexão precisa ser compatível com essa configuração.

### 3. Criar o arquivo .env

Crie um `.env` na raiz com as suas próprias credenciais:

```dotenv
GEMINI_API_KEY=
GROQ_API_KEY=
TYPESAFE_API_KEY=

DATABASE_URL=postgresql://usuario:senha@localhost:5432/assessor
MONGODB_URI=
QDRANT_URL=
QDRANT_API_KEY=
```

Para a integração opcional com o Google Calendar:

```dotenv
GOOGLE_OAUTH_CREDENTIALS=gcp-oauth.keys.json
```

O código também aceita `GOOGLE_CALENDAR_ACCESS_TOKEN` e `GOOGLE_CALENDAR_MCP_URL`. A chave `TYPESAFE_API_KEY` é necessária para que o juiz aprove as respostas que passam por essa etapa.

### 4. Indexar o FAQ

Confirme a presença de `data/FAQ_assessor_v1.1.pdf` e execute:

```bash
python -m app.ingest_faq
```

Esse comando recria o conteúdo da coleção de FAQ quando ela já possui registros. Execute na configuração de Qdrant destinada ao projeto.

### 5. Verificar os pré-requisitos

```bash
python scripts/verificar_prerequisitos.py
```

O script verifica dependências, configuração e acesso aos serviços. Ele não substitui um teste completo das funcionalidades nem verifica todo o esquema do PostgreSQL.

### 6. Iniciar a aplicação

```bash
python -m uvicorn app.main:app --reload
```

| Recurso | Endereço local |
| --- | --- |
| Chat | http://localhost:8000/ |
| Perfil financeiro | http://localhost:8000/perfil.html |
| Painel de monitoramento | http://localhost:8000/monitor.html |
| Documentação da API | http://localhost:8000/docs |
| Verificação de configuração | http://localhost:8000/health |

O endpoint `/health` informa problemas básicos de configuração; ele não realiza uma verificação completa das conexões externas.

### Google Calendar

Com as credenciais OAuth configuradas, execute a autorização local:

```bash
python -c "from app.tools.calendario_google import autenticar; print(autenticar())"
```

A conta precisa autorizar o acesso ao calendário. O token gerado deve permanecer fora do repositório.

### Servidor MCP

Para iniciar o servidor de ferramentas em um cliente compatível com `stdio`:

```bash
python -m app.mcp_server
```

## Exemplos de uso

Com os serviços configurados, alguns pedidos que exploram os fluxos do projeto são:

| Objetivo | Mensagem |
| --- | --- |
| Registrar despesa | “Gastei 25 reais com almoço hoje.” |
| Consultar histórico | “Quais foram meus gastos desta semana?” |
| Consultar saldo | “Qual é o meu saldo total?” |
| Atualizar um registro | “Altere o valor da transação de ID 12 para 30 reais.” |
| Criar compromisso | “Marque uma reunião de estudos em 10 de novembro de 2026, das 15h às 16h.” |
| Consultar agenda | “Quais compromissos tenho em 10 de novembro de 2026?” |
| Recuperar contexto | “O que eu te contei nas conversas anteriores?” |
| Consultar FAQ | “Como funciona o suporte do Assessor.ai?” |

Os exemplos de registro e atualização alteram dados. Para recuperar uma conversa anterior pela memória de longo prazo, ela precisa ter sido encerrada e resumida.

<img src="docs/assets/divisor.svg" width="1200" alt="" />

## Evolução do projeto

O desenvolvimento ampliou o escopo de um assistente conversacional para uma aplicação web com várias camadas:

1. **Ferramentas de finanças e agenda:** operações estruturadas em banco de dados.
2. **Especialização dos agentes:** separação entre roteamento, atendimento financeiro, agenda e FAQ.
3. **Aplicação web:** API com FastAPI e interface de chat no navegador.
4. **Memória e recuperação:** armazenamento das sessões e consulta semântica de resumos e documentos.
5. **Personalização:** cadastro de perfil e uso das preferências no atendimento financeiro.
6. **Integrações e acompanhamento:** Google Calendar, servidor MCP e painel de métricas.
7. **Avaliação das respostas:** inclusão de um juiz para verificar apoio nas evidências do turno.

Esses pontos apresentam as frentes implementadas, sem representar uma cronologia de commits ou resultados de testes.

## Aprendizados

O projeto permitiu trabalhar com problemas que vão além de enviar uma pergunta a um modelo: decidir qual agente deve responder, estruturar argumentos de ferramentas, separar dados relacionais de documentos e vetores, manter contexto entre sessões e lidar com falhas de serviços externos.

Também trouxe uma questão central para aplicações com IA: uma resposta convincente precisa ser acompanhada de evidências. Por isso, o Assessor combina ferramentas, recuperação de contexto e avaliação final, mantendo visíveis as limitações de cada etapa.

## Estado atual

Projeto acadêmico em desenvolvimento, voltado a execução local e demonstração das integrações implementadas.

O acesso aos dados depende da configuração do ambiente. O `user_id` identifica contextos de perfil e memória, mas não equivale a autenticação; as ferramentas financeiras e de agenda desta versão consultam a base configurada sem isolamento por usuário. Uma disponibilização pública exige evolução do controle de acesso e da separação dos dados.

<div align="center">

<sub>Desenvolvido no contexto do Ensino Médio Técnico da Germinare Tech.</sub>

</div>

