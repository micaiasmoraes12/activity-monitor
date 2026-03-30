# Extensão Chrome - Activity Monitor

Extensão para rastreamento preciso de tempo em abas e sites do Chrome.

## Instalação

1. Abra o Chrome e acesse `chrome://extensions/`

2. Ative o **Modo do desenvolvedor** (toggle no canto superior direito)

3. Clique em **Carregar expandida** (Load unpacked)

4. Selecione a pasta `chrome-extension/` deste projeto

5. A extensão aparecerá na barra de ferramentas do Chrome

## Como Funciona

- A extensão rastreia **automaticamente** todas as abas abertas
- Envia dados a cada 30 segundos para o app Python
- Armazena tempo total e tempo ativo (quando a aba está em foco)
- Detecta trocas entre abas

## Dados Rastreados

Para cada aba:
- URL completa
- Domínio (ex: youtube.com, github.com)
- Título da página
- Tempo total (incluindo abas em background)
- Tempo ativo (quando a aba está em foco)

## Integração com o App

O app Python deve estar rodando para receber os dados. 
Ele inicia automaticamente o servidor na porta 8765.

Se o app não estiver rodando, a extensão ainda funciona e 
armazena os dados localmente até reconectar.

## Desinstalar

1. Acesse `chrome://extensions/`
2. Encontre "Activity Monitor"
3. Clique em "Remover"
4. Confirme a remoção
