# spec_monitor.md
## Windows Activity Monitor — Especificação Técnica v2.0

> Baseado no PRD v2.0 (Março 2025)  
> Stack: Python 3.11+ · SQLite · Ollama (GLM-4 local) · pywin32 · pystray

---

## 1. Visão Geral

Ferramenta de monitoramento de produtividade **100% local e automática** para Windows. Captura silenciosamente a atividade do usuário ao longo do dia e gera, às 23h, um relatório em linguagem natural via **GLM-4 rodando localmente no Ollama** — sem nenhuma interação necessária e sem enviar dados para a internet.

**Diferencial central:** monitoramento totalmente passivo + relatório diário gerado por IA local, 100% offline.

---

## 2. Arquitetura de Módulos

```
activity-monitor/
├── monitor/
│   ├── collector.py        # daemon: win32gui polling a cada 10s, persistência SQLite
│   ├── db.py               # schema SQLite e helpers de query
│   ├── classifier.py       # categorização apps/URLs via categories.json
│   ├── browser.py          # captura URL Chrome/Edge/Firefox via UI Automation
│   ├── idle_detector.py    # GetLastInputInfo + detecção de tela bloqueada
│   └── session_builder.py  # agrupa eventos brutos em sessões
├── reporter/
│   ├── aggregator.py       # queries SQLite: top apps, categorias, picos
│   ├── scorer.py           # calcula score de produtividade diário
│   ├── llm_client.py       # chamada ao Ollama (GLM-4 local) com prompt estruturado
│   └── renderer.py         # salva relatório em .md e .html
├── tray/
│   ├── app.py              # pystray: ícone, menu, badge de score
│   └── notifications.py    # toast Windows com win10toast/plyer
├── config/
│   ├── settings.json       # modelo Ollama, horário, threshold idle, preferências
│   ├── categories.json     # regras de classificação app → categoria
│   └── blocklist.json      # apps que nunca aparecem nos dados
├── main.py                 # entrypoint: inicia daemon + tray + scheduler
├── install.py              # setup: dependências, startup, config inicial
└── requirements.txt
```

---

## 3. Stack Tecnológica

| Componente | Tecnologia | Nota |
|---|---|---|
| Linguagem | Python 3.11+ | |
| APIs Windows (janelas) | pywin32 / win32gui | |
| APIs Windows (idle) | win32api.GetLastInputInfo | Threshold configurável |
| Captura de URLs | pywinauto / UI Automation | Sem extensão de browser |
| Banco de dados | SQLite (stdlib) | Local, sem limite de tempo |
| System Tray | pystray + Pillow | |
| Agendamento | APScheduler | Trigger às 23h (configurável) |
| LLM | Ollama + GLM-4 | Roda 100% local, zero internet, endpoint `http://localhost:11434` |
| Notificações | win10toast / plyer | Toast nativo Windows 10/11 |
| Empacotamento | PyInstaller | .exe standalone |

---

## 4. Schema do Banco de Dados (SQLite)

Localização: `%APPDATA%\ActivityMonitor\`  
Retenção: **ilimitada** (sem o limite de 45 dias de concorrentes).

| Tabela | Descrição |
|---|---|
| `events` | Captura bruta a cada 10s |
| `sessions` | Sessões agrupadas por app (início, fim, duração, URL, categoria) |
| `daily_summaries` | Sumário por dia com JSON de top apps e tempo por categoria |
| `categories` | Mapeamento app/URL → categoria + flag `is_productive` |
| `reports` | Metadados dos relatórios gerados (data, caminho, score) |

---

## 5. Módulos — Comportamento Esperado

### 5.1 Collector (daemon)
- Polling via `win32gui.GetForegroundWindow()` a cada **10s** (configurável)
- Registra: nome do processo, título da janela, URL (quando browser), timestamp, duração
- Para de coletar quando a tela está bloqueada
- Inicia automaticamente com o Windows via registro `HKCU\Run`

### 5.2 Idle Detector
- Usa `win32api.GetLastInputInfo` — threshold padrão: **60s** (configurável)
- Detecta também **tela bloqueada** (melhoria sobre soluções que detectam apenas sleep)

### 5.3 Browser URL Capture
- Captura URLs do Chrome, Edge e Firefox via **UI Automation do Windows**
- Nenhuma extensão de browser necessária

### 5.4 Session Builder
- Agrupa eventos consecutivos do mesmo app em sessões com duração total

### 5.5 Classifier
- `categories.json` editável com regras de pattern matching (glob e regex)
- Categorias padrão pré-configuradas no `install.py`
- Distinção entre apps produtivos e não-produtivos (entra no score)
- `blocklist.json`: apps que nunca aparecem nos dados (ex: apps bancários)
- O GLM-4 pode sugerir novas categorias no relatório para apps não classificados

### 5.6 Aggregator
- Compila dados do dia: top 15 apps, tempo por categoria, linha do tempo, picos e idle
- Compara com média dos últimos 7 dias quando disponível

### 5.7 Scorer
- Calcula score de produtividade diário: `% tempo em apps produtivos vs. distrações`
- Score exposto no badge do System Tray (atualizado a cada hora) e no relatório

### 5.8 LLM Client (Ollama)
- Conecta ao Ollama em `http://localhost:11434/api/chat` usando o modelo `glm4`
- Envia payload estruturado (apenas nomes de app, categorias, durações — **nunca** títulos completos de janelas ou conteúdo de arquivos)
- Nenhum dado sai da máquina — inferência 100% local
- GLM-4 gera: sumário executivo, análise de padrões, destaques, alertas e sugestões para o dia seguinte
- Exemplo de chamada:
```python
import requests

def gerar_relatorio(payload: dict) -> str:
    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": "glm4",
            "messages": [{"role": "user", "content": prompt_com(payload)}],
            "stream": False
        }
    )
    return response.json()["message"]["content"]
```

### 5.9 Renderer
- Salva relatório em `.md` e `.html` em `%APPDATA%\ActivityMonitor\reports\`
- Notificação toast no Windows ao finalizar

### 5.10 System Tray
- Indicador visual de status: monitorando / pausado / gerando relatório
- Menu: Ver relatório de hoje | Histórico | Pausar | Forçar geração agora | Configurações | Sair
- Badge com score do dia

---

## 6. Requisitos Não Funcionais

| Métrica | Limite |
|---|---|
| CPU em coleta normal | < 1% |
| CPU pico (geração de relatório) | < 5% |
| RAM em operação | < 80 MB |
| Startup do daemon no boot | < 3s |
| Tempo de geração do relatório | < 30s |
| Compatibilidade | Windows 10 (build 1903+) e Windows 11 |

---

## 7. KPIs de Qualidade

| Métrica | Meta | Como medir |
|---|---|---|
| Precisão de captura de tempo | > 98% | Amostragem manual |
| Cobertura de apps categorizados | > 90% | Revisão manual pós-uso |
| Qualidade percebida do relatório | 4,5/5 | Auto-avaliação semanal |

---

## 8. Privacidade e Segurança

- Todos os dados ficam **exclusivamente no SQLite local** — sem sincronização ou backup em nuvem
- **Nenhum dado sai da máquina** — a inferência do GLM-4 é feita pelo Ollama localmente
- Não há API key, conta externa ou dependência de internet
- Payload enviado ao Ollama: apenas nomes de app, categorias e durações — sem títulos de janela, senhas ou conteúdo de arquivos
- Blocklist configurável para apps e domínios sensíveis
- Pausa instantânea via System Tray

---

## 9. Backlog de Features (Priorizado)

| ID | Feature | Descrição | Prior. | Esforço |
|---|---|---|---|---|
| F-01 | Daemon de coleta | win32gui polling + SQLite | Alta | 3d |
| F-02 | Detecção idle | GetLastInputInfo + tela bloqueada | Alta | 1d |
| F-03 | Captura de URLs | UI Automation sem extensão | Alta | 2d |
| F-04 | Startup automático | HKCU\Run + install.py | Alta | 0,5d |
| F-05 | Gerador de relatório | Agregação + Ollama GLM-4 local + MD/HTML | Alta | 2d |
| F-06 | System Tray | Ícone, menu, badge, toast | Alta | 1d |
| F-07 | Categorização auto | categories.json + blocklist | Alta | 1d |
| F-08 | Score diário | % tempo produtivo vs. distração | Média | 1d |
| F-09 | Comparativo 7 dias | Histórico de scores no relatório | Média | 1d |
| F-10 | Relatório HTML rico | Gráficos de barras em HTML estático | Média | 2d |
| F-11 | Config GUI | Janela: API key, horário, threshold | Baixa | 2d |
| F-12 | Dashboard local | Servidor HTTP local (Flask) | Baixa | 3d |
| F-13 | Export CSV/JSON | Exportar dados brutos | Baixa | 0,5d |

**MVP (F-01 a F-07):** estimativa de 2 dias de desenvolvimento.

---

## 10. Critérios de Aceitação do MVP

- [ ] Daemon inicia automaticamente com o Windows sem interação manual
- [ ] Após 24h, banco SQLite sem lacunas superiores a 30s
- [ ] URLs do Chrome e Edge capturadas corretamente sem extensão
- [ ] Idle detectado corretamente (validado em 5 períodos por amostragem manual)
- [ ] Relatório gerado automaticamente às 23h com os top 5 apps corretos
- [ ] Score de produtividade aparece no relatório e no badge do tray
- [ ] CPU nunca excede 2% por mais de 1 minuto em operação normal
- [ ] Usuário consegue pausar, retomar e forçar geração pelo System Tray
- [ ] Relatório HTML abre no browser padrão pelo menu do tray

---

## 11. Plano de Desenvolvimento (5 Sessões)

| Sessão | Foco | Entregas |
|---|---|---|
| 1 | Coleta base | `collector.py`, `db.py`, `idle_detector.py`, startup automático |
| 2 | Coleta completa | `browser.py`, `session_builder.py`, `classifier.py` + `categories.json` |
| 3 | Relatório | `aggregator.py`, `scorer.py`, `llm_client.py` (Ollama), `renderer.py` |
| 4 | UX | `pystray`, badge, toast, APScheduler às 23h |
| 5 | Instalação & polish | `install.py`, testes de integração, PyInstaller `.exe` |

---

*Windows Activity Monitor — spec v2.0 · Dados 100% locais · GLM-4 via Ollama para insights diários*
