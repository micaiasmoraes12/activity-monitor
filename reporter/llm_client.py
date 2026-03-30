"""
llm_client.py — Cliente Ollama (GLM-4 local) para gerar relatório em linguagem natural.
"""

import logging
import requests
from typing import Optional

from monitor.config import get_settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60


class LLMClient:
    """Cliente para chamada ao Ollama local."""
    
    def __init__(self) -> None:
        cfg = get_settings()
        self.model = cfg.get("ollama_model", "glm4")
        self.url = cfg.get("ollama_url", "http://localhost:11434/api/chat")
    
    def is_available(self) -> bool:
        """Verifica se o Ollama está rodando."""
        try:
            resp = requests.get(
                "http://localhost:11434/api/tags",
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False
    
    def generate_report(self, payload: dict) -> Optional[str]:
        """
        Gera relatório de produtividade via GLM-4.
        
        Args:
            payload: dict com dados do dia (top_apps, categories, score, etc.)
        
        Returns:
            str com relatório em markdown, ou None se falhar
        """
        prompt = self._build_prompt(payload)
        
        try:
            response = requests.post(
                self.url,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self._system_prompt()},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
                timeout=TIMEOUT_SECONDS,
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("message", {}).get("content")
            else:
                logger.error("Ollama retornou erro: %s %s", response.status_code, response.text)
                return None
                
        except requests.exceptions.ConnectionError:
            logger.error("Não foi possível conectar ao Ollama em %s", self.url)
            return None
        except requests.exceptions.Timeout:
            logger.error("Timeout ao chamar Ollama (timeout=%ds)", TIMEOUT_SECONDS)
            return None
        except Exception:
            logger.exception("Erro inesperado ao chamar Ollama")
            return None
    
    def _system_prompt(self) -> str:
        return """Você é um assistente de produtividade pessoal que analiza dados de monitoramento de atividades do usuário.

Sua tarefa é gerar um relatório diário de produtividade em português brasileiro, com:
- Sumário executivo (2-3 frases)
- Análise de padrões de uso
- Destaques (melhor e pior momento do dia)
- Alertas sobre posibles problemas
- Sugestões para o dia seguinte

Seja conciso, objetivo e construtivo. Use emojis apenas para destacar métricas importantes.

NÃO inclua dados sensíveis como títulos de janelas, URLs completas ou conteúdo de arquivos."""


    def _build_prompt(self, payload: dict) -> str:
        """Constrói prompt estruturado com os dados do dia."""
        date = payload.get("date", "hoje")
        score = payload.get("score", 0)
        top_apps = payload.get("top_apps", [])
        categories = payload.get("category_breakdown", {})
        total_active = payload.get("total_active_sec", 0)
        peaks = payload.get("peaks", [])
        
        apps_text = "\n".join([
            f"- {a['process_name']}: {a.get('duration_hm', '0m')} ({a.get('category', 'Outro')})"
            for a in top_apps[:10]
        ]) or "Nenhum app registrado"
        
        cats_text = "\n".join([
            f"- {cat}: {self._sec_to_hm(sec)}"
            for cat, sec in sorted(categories.items(), key=lambda x: x[1], reverse=True)
        ]) or "Nenhuma categoria"
        
        peaks_text = "\n".join([
            f"- {p['app']}: {self._sec_to_hm(p['duration'])} ({p.get('start_time', '')[:10]})"
            for p in peaks[:3]
        ]) or "Sem picos registrados"
        
        prompt = f"""## Relatório de Produtividade - {date}

### Métricas Gerais
- **Score de Produtividade:** {score}%
- **Tempo Total Ativo:** {self._sec_to_hm(total_active)}

### Top 10 Apps
{apps_text}

### Tempo por Categoria
{cats_text}

### Principais Períodos de Foco
{peaks_text}

Por favor, gere um relatório em português brasileiro com:
1. Sumário executivo (2-3 frases)
2. Análise de padrões de uso
3. Destaques do dia
4. Alertas (se houver)
5. Sugestões para o próximo dia

Mantenha o relatório conciso e útil."""
        
        return prompt
    
    def _sec_to_hm(self, sec: int) -> str:
        """Converte segundos para string 'Xh Ym'."""
        h = sec // 3600
        m = (sec % 3600) // 60
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m"


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
