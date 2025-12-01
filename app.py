from supabase import create_client, Client
from flask import Flask, render_template, request, jsonify
import json
import os
from groq import Groq
from dotenv import load_dotenv
import qrcode
from io import BytesIO
import base64
from collections import Counter

# -----------------------------
# Configuração
# -----------------------------
load_dotenv()

# Supabase - USAR VARIÁVEIS DE AMBIENTE!
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ ERRO: SUPABASE_URL ou SUPABASE_KEY não encontradas!")
    print("   Adiciona estas variáveis ao .env ou às Environment Variables do Render")
    supabase = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase conectado!")

# Groq
groq_api_key = os.getenv("GROQ_API_KEY")
if groq_api_key:
    groq_client = Groq(api_key=groq_api_key)
    print("✅ Groq API conectada!")
else:
    print("❌ GROQ_API_KEY não encontrada!")
    groq_client = None

# Flask
app = Flask(__name__)


# -----------------------------
# Funções Supabase
# -----------------------------
def guardar_protocolo(protocolo: dict):
    """Guarda um protocolo no Supabase e retorna o ID"""
    if not supabase:
        print("❌ Supabase não inicializado")
        return None
    try:
        response = supabase.table("protocolos").insert(protocolo).execute()
        if response.data:
            print(f"✅ Protocolo guardado com ID: {response.data[0]['id']}")
            return response.data[0]["id"]
        return None
    except Exception as e:
        print(f"❌ Erro ao guardar protocolo: {e}")
        return None


def listar_protocolos(limite=None):
    """Lista protocolos ordenados por data de criação"""
    if not supabase:
        return []
    try:
        query = supabase.table("protocolos").select("*").order("created_at", desc=True)
        if limite:
            query = query.limit(limite)
        response = query.execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"❌ Erro ao listar protocolos: {e}")
        return []


def obter_protocolo_por_id(id: int):
    """Obtém um protocolo específico pelo ID"""
    if not supabase:
        return None
    try:
        response = supabase.table("protocolos").select("*").eq("id", id).single().execute()
        return response.data
    except Exception as e:
        print(f"❌ Erro ao obter protocolo {id}: {e}")
        return None


def pesquisar_protocolos(termo: str):
    """Pesquisa protocolos por título, resumo ou autor"""
    if not supabase:
        return []
    try:
        response = supabase.table("protocolos").select("*").or_(
            f"titulo.ilike.%{termo}%,resumo.ilike.%{termo}%,autor.ilike.%{termo}%"
        ).order("created_at", desc=True).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"❌ Erro ao pesquisar: {e}")
        # Fallback: buscar tudo e filtrar em Python
        protocolos = listar_protocolos()
        termo_lower = termo.lower()
        return [
            p for p in protocolos
            if termo_lower in (p.get("titulo") or "").lower()
            or termo_lower in (p.get("resumo") or "").lower()
            or termo_lower in (p.get("autor") or "").lower()
        ]


def incrementar_contador(id: int, campo: str):
    """Incrementa um contador (gostos, nao_gostos, visualizacoes)"""
    if not supabase:
        return False
    try:
        # Primeiro buscar valor atual
        protocolo = obter_protocolo_por_id(id)
        if not protocolo:
            return False
        
        valor_atual = protocolo.get(campo, 0) or 0
        novo_valor = valor_atual + 1
        
        # Atualizar
        response = supabase.table("protocolos").update({campo: novo_valor}).eq("id", id).execute()
        return response.data is not None
    except Exception as e:
        print(f"❌ Erro ao incrementar {campo}: {e}")
        return False


# -----------------------------
# Funções Auxiliares
# -----------------------------
def gerar_qr_code(url):
    """Gera QR Code em base64"""
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"


def to_string(value):
    """Converte valor para string, juntando listas com newlines"""
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return str(value) if value else ""


def parse_json_field(value, default=None):
    """Parse de campo JSON/TEXT, retornando default se falhar"""
    if default is None:
        default = {}
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except:
            return default
    return default


def preparar_protocolo_para_template(protocolo):
    """Prepara um protocolo da BD para ser usado no template"""
    if not protocolo:
        return None
    
    # Parse campos que podem ser JSON em formato texto
    protocolo["disciplinas"] = parse_json_field(protocolo.get("disciplinas"), [])
    protocolo["anos"] = parse_json_field(protocolo.get("anos"), [])
    protocolo["seguranca"] = parse_json_field(protocolo.get("seguranca_json") or protocolo.get("seguranca"), {})
    protocolo["quiz"] = parse_json_field(protocolo.get("quiz_json") or protocolo.get("quiz"), [])
    protocolo["diferenciacao"] = parse_json_field(protocolo.get("diferenciacao_json"), {})
    protocolo["competencias"] = parse_json_field(protocolo.get("competencias"), [])
    protocolo["objetivos"] = parse_json_field(protocolo.get("objetivos"), [])
    
    return protocolo


# -----------------------------
# Rotas Flask
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/gerar")
def gerar():
    return render_template("gerar_protocolo.html")


@app.route("/consultar")
def consultar():
    return render_template("consultar_protocolos.html")


@app.route("/api/stats")
def get_stats():
    """Endpoint para dashboard de estatísticas"""
    try:
        protocolos = listar_protocolos()
        
        total = len(protocolos)
        total_views = sum(p.get("visualizacoes", 0) or 0 for p in protocolos)
        
        # Top 5 mais populares
        mais_populares = sorted(
            protocolos, 
            key=lambda x: (x.get("gostos", 0) or 0, x.get("visualizacoes", 0) or 0), 
            reverse=True
        )[:5]
        
        # Contagem por disciplina
        todas_disciplinas = []
        for p in protocolos:
            disc = parse_json_field(p.get("disciplinas"), [])
            todas_disciplinas.extend(disc)
        
        disc_counter = Counter(todas_disciplinas)
        por_disciplina = [{"disciplina": k, "count": v} for k, v in disc_counter.most_common()]
        
        # Últimos 5
        ultimos = protocolos[:5]
        
        return jsonify({
            "total_protocolos": total,
            "total_visualizacoes": total_views,
            "mais_populares": mais_populares,
            "por_disciplina": por_disciplina,
            "ultimos": ultimos
        })
    except Exception as e:
        print(f"❌ Erro ao obter estatísticas: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/generate_protocol", methods=["POST"])
def generate_protocol():
    """Gera um novo protocolo usando IA"""
    data = request.get_json()
    autor = data.get("autor", "")
    anos = data.get("anos", [])
    disciplinas = data.get("disciplinas", [])
    resumo_usuario = data.get("resumo", "")
    titulo_usuario = data.get("titulo", "") or "(Sem título)"

    print(f"📝 A gerar protocolo pedagógico completo: {titulo_usuario}")
    
    protocolo_gerado = gerar_protocolo_ia(titulo_usuario, resumo_usuario, anos, disciplinas)
    protocolo_gerado["autor"] = autor
    protocolo_gerado["anos"] = anos
    protocolo_gerado["disciplinas"] = disciplinas
    
    return jsonify({"status": "ok", "protocolo": protocolo_gerado})


@app.route("/regenerate_protocol", methods=["POST"])
def regenerate_protocol():
    """Regenera protocolo com base em feedback"""
    data = request.get_json()
    protocolo_anterior = data.get("protocolo_anterior", {})
    feedback = data.get("feedback", "")
    
    print(f"🔄 A regenerar protocolo com feedback: {feedback[:50]}...")
    
    protocolo_novo = regenerar_protocolo_ia(protocolo_anterior, feedback)
    protocolo_novo["autor"] = protocolo_anterior.get("autor", "")
    protocolo_novo["anos"] = protocolo_anterior.get("anos", [])
    protocolo_novo["disciplinas"] = protocolo_anterior.get("disciplinas", [])
    
    return jsonify({"status": "ok", "protocolo": protocolo_novo})


@app.route("/save_protocol", methods=["POST"])
def save_protocol():
    """Guarda um protocolo na base de dados"""
    data = request.get_json()
    protocolo = data.get("protocolo", {})
    
    print(f"💾 A guardar protocolo: {protocolo.get('titulo', '(sem título)')}")
    
    try:
        # Preparar registo - adaptar aos campos da tua tabela
        registro = {
            "titulo": to_string(protocolo.get("titulo", "")),
            "subtitulo": to_string(protocolo.get("subtitulo", "")),
            "duracao": to_string(protocolo.get("duracao", "")),
            "competencias": json.dumps(protocolo.get("competencias", [])),
            "objetivos": json.dumps(protocolo.get("objetivos", [])),
            "contextualizacao": to_string(protocolo.get("contextualizacao", "")),
            "resumo": to_string(protocolo.get("resumo", "")),
            "materiais": to_string(protocolo.get("materiais", "")),
            "pre_experiencia": to_string(protocolo.get("pre_experiencia", "")),
            "procedimento": to_string(protocolo.get("procedimento", "")),
            "pos_experiencia": to_string(protocolo.get("pos_experiencia", "")),
            "resultados_esperados": to_string(protocolo.get("resultados_esperados", "")),
            "seguranca_json": json.dumps(protocolo.get("seguranca", {})),
            "quiz_json": json.dumps(protocolo.get("quiz", [])),
            "diferenciacao_json": json.dumps(protocolo.get("diferenciacao", {})),
            "recursos_extras": to_string(protocolo.get("recursos_extras", "")),
            "disciplinas": json.dumps(protocolo.get("disciplinas", [])),
            "anos": json.dumps(protocolo.get("anos", [])),
            "autor": to_string(protocolo.get("autor", "")),
            "gostos": 0,
            "nao_gostos": 0,
            "visualizacoes": 0
        }

        protocol_id = guardar_protocolo(registro)
        
        if protocol_id:
            print("✅ Protocolo pedagógico guardado com sucesso!")
            return jsonify({"status": "ok", "id": protocol_id})
        else:
            return jsonify({"status": "erro", "message": "Falha ao guardar no Supabase"}), 500
            
    except Exception as e:
        print(f"❌ Erro ao guardar: {e}")
        return jsonify({"status": "erro", "message": str(e)}), 500


@app.route("/search_protocols")
def search_protocols():
    """Pesquisa protocolos por termo"""
    q = request.args.get("q", "").strip()
    
    if q:
        resultados = pesquisar_protocolos(q)
    else:
        resultados = listar_protocolos()
    
    # Preparar para JSON response
    for r in resultados:
        r["disciplinas"] = parse_json_field(r.get("disciplinas"), [])
        r["anos"] = parse_json_field(r.get("anos"), [])
    
    return jsonify(resultados)


@app.route("/protocolo/<int:id>")
def ver_protocolo(id):
    """Visualiza um protocolo específico"""
    # Incrementar visualizações
    incrementar_contador(id, "visualizacoes")
    
    # Obter protocolo
    protocolo = obter_protocolo_por_id(id)
    
    if not protocolo:
        return "Protocolo não encontrado", 404
    
    # Preparar para template
    protocolo = preparar_protocolo_para_template(protocolo)
    
    # Gerar QR Code
    protocolo["qr_code"] = gerar_qr_code(request.host_url + f"protocolo/{id}")
    
    return render_template("protocolo.html", protocolo=protocolo)


@app.route("/avaliar_protocolo/<int:id>", methods=["POST"])
def avaliar_protocolo(id):
    """Avalia um protocolo (gosto/não gosto)"""
    data = request.get_json()
    tipo = data.get("tipo")
    
    if tipo not in ['gosto', 'nao_gosto']:
        return jsonify({"status": "erro", "message": "Tipo inválido"}), 400
    
    campo = "gostos" if tipo == "gosto" else "nao_gostos"
    
    if incrementar_contador(id, campo):
        # Buscar valores atualizados
        protocolo = obter_protocolo_por_id(id)
        return jsonify({
            "status": "ok",
            "gostos": protocolo.get("gostos", 0) if protocolo else 0,
            "nao_gostos": protocolo.get("nao_gostos", 0) if protocolo else 0
        })
    
    return jsonify({"status": "erro", "message": "Erro ao avaliar"}), 500


# -----------------------------
# Funções IA (Groq)
# -----------------------------
def gerar_protocolo_ia(titulo, resumo, anos, disciplinas):
    """Gera protocolo experimental PEDAGÓGICO COMPLETO usando IA"""
    
    if not groq_client:
        print("❌ Cliente Groq não inicializado")
        return criar_protocolo_fallback(titulo, resumo)
    
    prompt = f"""És um especialista em EDUCAÇÃO EM CIÊNCIAS com experiência em pedagogia das ciências experimentais, currículo português do ensino básico e segurança em laboratório escolar.

Cria um protocolo experimental COMPLETO, PEDAGÓGICO e SEGURO em português de Portugal.

INFORMAÇÃO BASE:
- Título: {titulo}
- Descrição: {resumo}
- Anos letivos: {', '.join(anos) if anos else 'Não especificado'}
- Disciplinas: {', '.join(disciplinas) if disciplinas else 'Não especificado'}

INSTRUÇÕES COMPLETAS:

1. TÍTULO: Se vazio, cria título apelativo. Adiciona subtítulo com conceito científico.

2. METADADOS:
   - Duração estimada (ex: "45-50 minutos")
   - 2-3 competências (raciocínio, trabalho prático, comunicação)
   - 2-4 objetivos claros com verbos de ação

3. CONTEXTUALIZAÇÃO: Parágrafo motivador ligando ao quotidiano dos alunos.

4. MATERIAIS: Lista detalhada com quantidades. Indicar alternativas quando possível.

5. ESTRUTURA PEDAGÓGICA:
   - PRÉ-EXPERIÊNCIA: Questões para ativar conhecimentos (2-3 questões)
   - PROCEDIMENTO: 6-10 passos detalhados, cada um com "💡 Observar:" 
   - PÓS-EXPERIÊNCIA: Questões para discussão e sistematização
   - RESULTADOS ESPERADOS: O que os alunos devem observar

6. SEGURANÇA (CRÍTICO):
   Retornar objeto JSON com:
   - nivel_risco: "Baixo", "Médio" ou "Alto"
   - riscos: lista de riscos específicos
   - epi: equipamento de proteção necessário
   - supervisao: tipo de supervisão necessária
   - cuidados: procedimentos de segurança
   - primeiros_socorros: o que fazer em caso de acidente
   - descarte: como descartar materiais

7. QUIZ (5 PERGUNTAS VARIADAS):
   Retornar array de objetos com:
   [
     {{
       "tipo": "multipla_escolha",
       "pergunta": "...",
       "opcoes": ["A) ...", "B) ...", "C) ...", "D) ..."],
       "resposta_correta": "B",
       "explicacao": "..."
     }},
     {{
       "tipo": "verdadeiro_falso",
       "afirmacao": "...",
       "resposta_correta": true,
       "explicacao": "..."
     }},
     {{
       "tipo": "aberta",
       "pergunta": "...",
       "resposta_sugerida": "..."
     }}
   ]
   Criar 2 escolha múltipla, 1 V/F, 1 observação, 1 reflexiva.

8. DIFERENCIAÇÃO:
   Retornar objeto com:
   - simplificacao: [2-3 sugestões]
   - aprofundamento: [2-3 desafios]
   - inclusao: [1-2 adaptações]

9. RECURSOS EXTRAS: Array com 2-3 sugestões de recursos complementares.

FORMATO JSON (responde APENAS com isto, sem markdown):
{{
  "titulo": "...",
  "subtitulo": "...",
  "duracao": "...",
  "competencias": ["...", "..."],
  "objetivos": ["...", "..."],
  "contextualizacao": "...",
  "resumo": "Breve resumo da experiência",
  "materiais": "Lista com quantidades...",
  "pre_experiencia": "Questões para antes...",
  "procedimento": "Passos com 💡 Observar...",
  "pos_experiencia": "Discussão e conclusões...",
  "resultados_esperados": "O que observar...",
  "seguranca": {{
    "nivel_risco": "...",
    "riscos": "...",
    "epi": "...",
    "supervisao": "...",
    "cuidados": "...",
    "primeiros_socorros": "...",
    "descarte": "..."
  }},
  "quiz": [...],
  "diferenciacao": {{
    "simplificacao": [...],
    "aprofundamento": [...],
    "inclusao": [...]
  }},
  "recursos_extras": [...]
}}

IMPORTANTE: Linguagem adequada aos anos {', '.join(anos) if anos else 'do ensino básico'}. Segurança é PRIORITÁRIA."""

    try:
        print("🤖 A gerar protocolo pedagógico completo...")
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system", 
                    "content": "És um especialista em educação em ciências. Crias protocolos pedagógicos completos, seguros e alinhados com o currículo português. Respondes SEMPRE em JSON válido, sem markdown."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=3500
        )
        
        resposta_texto = response.choices[0].message.content.strip()
        print("📥 Resposta recebida do Groq")
        
        # Limpar markdown se presente
        if resposta_texto.startswith("```json"):
            resposta_texto = resposta_texto[7:]
        if resposta_texto.startswith("```"):
            resposta_texto = resposta_texto[3:]
        if resposta_texto.endswith("```"):
            resposta_texto = resposta_texto[:-3]
        resposta_texto = resposta_texto.strip()
        
        protocolo = json.loads(resposta_texto)
        print("✅ Protocolo pedagógico gerado com sucesso!")
        
        return protocolo
        
    except json.JSONDecodeError as e:
        print(f"❌ Erro ao processar JSON: {e}")
        return criar_protocolo_fallback(titulo, resumo)
    except Exception as e:
        print(f"❌ Erro ao gerar protocolo: {e}")
        return criar_protocolo_fallback(titulo, resumo)


def regenerar_protocolo_ia(protocolo_anterior, feedback):
    """Regenera protocolo com base em feedback do utilizador"""
    
    if not groq_client:
        print("❌ Cliente Groq não inicializado")
        return protocolo_anterior
    
    prompt = f"""Melhora este protocolo experimental com base no feedback do utilizador.

PROTOCOLO ANTERIOR:
{json.dumps(protocolo_anterior, indent=2, ensure_ascii=False)}

FEEDBACK DO UTILIZADOR:
{feedback}

INSTRUÇÕES:
- Mantém a estrutura JSON completa
- Melhora apenas o que foi pedido no feedback
- Mantém segurança e qualidade pedagógica
- Responde APENAS com JSON válido, sem markdown

Retorna o protocolo melhorado no MESMO formato JSON."""

    try:
        print("🔄 A regenerar protocolo...")
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system", 
                    "content": "És um especialista em melhorar protocolos experimentais. Respondes SEMPRE em JSON válido, sem markdown."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=3500
        )
        
        resposta_texto = response.choices[0].message.content.strip()
        
        # Limpar markdown
        if resposta_texto.startswith("```json"):
            resposta_texto = resposta_texto[7:]
        if resposta_texto.startswith("```"):
            resposta_texto = resposta_texto[3:]
        if resposta_texto.endswith("```"):
            resposta_texto = resposta_texto[:-3]
        resposta_texto = resposta_texto.strip()
        
        protocolo_novo = json.loads(resposta_texto)
        print("✅ Protocolo regenerado!")
        return protocolo_novo
        
    except Exception as e:
        print(f"❌ Erro ao regenerar: {e}")
        return protocolo_anterior


def criar_protocolo_fallback(titulo, resumo):
    """Protocolo básico em caso de erro da IA"""
    return {
        "titulo": titulo or "Protocolo Experimental",
        "subtitulo": "Protocolo experimental",
        "duracao": "45 minutos",
        "competencias": ["Trabalho prático", "Raciocínio científico"],
        "objetivos": ["Realizar a experiência proposta", "Observar e registar resultados"],
        "contextualizacao": resumo or "Experiência científica para explorar conceitos fundamentais.",
        "resumo": resumo or "Experiência científica.",
        "materiais": "⚠️ Erro ao gerar materiais. Por favor, tenta novamente.",
        "pre_experiencia": "1. O que achas que vai acontecer?\n2. Já observaste algo semelhante no dia-a-dia?",
        "procedimento": "⚠️ Erro ao gerar procedimento. Por favor, tenta novamente.",
        "pos_experiencia": "1. O que observaste?\n2. Correspondeu às tuas expectativas?",
        "resultados_esperados": "A definir após nova geração.",
        "seguranca": {
            "nivel_risco": "Médio",
            "riscos": "Análise de segurança não disponível - avalia com cuidado.",
            "epi": "Óculos e bata de laboratório recomendados.",
            "supervisao": "Supervisão de professor obrigatória.",
            "cuidados": "Manter supervisão constante.",
            "primeiros_socorros": "Contactar responsável em caso de acidente.",
            "descarte": "Seguir normas do laboratório."
        },
        "quiz": [],
        "diferenciacao": {
            "simplificacao": ["Reduzir número de passos"],
            "aprofundamento": ["Investigar variáveis adicionais"],
            "inclusao": ["Trabalho em pares"]
        },
        "recursos_extras": ["Manual escolar", "Vídeos educativos"]
    }


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Portal de Protocolos Experimentais")
    print("   Com Supabase + Groq AI")
    print("=" * 50)
    
    if not supabase:
        print("⚠️  AVISO: Supabase não configurado!")
    
    if not groq_client:
        print("⚠️  AVISO: Groq não configurado!")
    
    port = int(os.environ.get("PORT", 5000))
    print(f"📍 Servidor: http://0.0.0.0:{port}")
    
    app.run(host='0.0.0.0', port=port, debug=False)