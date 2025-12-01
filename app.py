from flask import Flask, render_template, request, jsonify
import sqlite3
import json
import os
from groq import Groq
from dotenv import load_dotenv
import qrcode
from io import BytesIO
import base64

app = Flask(__name__)
DB_NAME = "protocolos.db"

# Carregar chave do Groq
load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY")
print("⚠️ DEBUG - API Key Groq carregada:", groq_api_key[:20] + "..." if groq_api_key else "❌ NÃO ENCONTRADA")

# Inicializar cliente Groq
client = Groq(api_key=groq_api_key)

def criar_base_de_dados():
    if not os.path.exists(DB_NAME):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE protocolos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT,
            subtitulo TEXT,
            duracao TEXT,
            competencias TEXT,
            objetivos TEXT,
            contextualizacao TEXT,
            resumo TEXT,
            materiais TEXT,
            pre_experiencia TEXT,
            procedimento TEXT,
            pos_experiencia TEXT,
            resultados_esperados TEXT,
            seguranca_json TEXT,
            quiz_json TEXT,
            diferenciacao_json TEXT,
            recursos_extras TEXT,
            disciplinas TEXT,
            anos TEXT,
            autor TEXT,
            gostos INTEGER DEFAULT 0,
            nao_gostos INTEGER DEFAULT 0,
            visualizacoes INTEGER DEFAULT 0,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
        conn.close()
        print("✅ Base de dados criada com estrutura completa!")
    else:
        # Atualizar BD existente
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Verificar e adicionar colunas novas
        colunas_necessarias = [
            ("subtitulo", "TEXT"),
            ("duracao", "TEXT"),
            ("competencias", "TEXT"),
            ("objetivos", "TEXT"),
            ("contextualizacao", "TEXT"),
            ("pre_experiencia", "TEXT"),
            ("procedimento", "TEXT"),
            ("pos_experiencia", "TEXT"),
            ("resultados_esperados", "TEXT"),
            ("seguranca_json", "TEXT"),
            ("quiz_json", "TEXT"),
            ("diferenciacao_json", "TEXT"),
            ("recursos_extras", "TEXT"),
            ("visualizacoes", "INTEGER DEFAULT 0"),
            ("data_criacao", "TIMESTAMP")
        ]
        
        for coluna, tipo in colunas_necessarias:
            try:
                c.execute(f"SELECT {coluna} FROM protocolos LIMIT 1")
            except:
                if "DEFAULT" in tipo:
                    tipo_base = tipo.split("DEFAULT")[0].strip()
                    c.execute(f"ALTER TABLE protocolos ADD COLUMN {coluna} {tipo_base}")
                    if "data_criacao" in coluna:
                        c.execute(f"UPDATE protocolos SET {coluna} = CURRENT_TIMESTAMP WHERE {coluna} IS NULL")
                else:
                    c.execute(f"ALTER TABLE protocolos ADD COLUMN {coluna} {tipo}")
                print(f"✅ Coluna '{coluna}' adicionada!")
        
        conn.commit()
        conn.close()
        print("✅ Base de dados verificada e atualizada.")

# ----------------- ROTAS -----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/gerar")
def gerar():
    return render_template("gerar_protocolo.html")

@app.route("/consultar")
def consultar():
    return render_template("consultar_protocolos.html")

# ROTA: Dashboard de estatísticas
@app.route("/api/stats")
def get_stats():
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) as total FROM protocolos")
        total = c.fetchone()['total']
        
        c.execute("SELECT SUM(visualizacoes) as total_views FROM protocolos")
        total_views = c.fetchone()['total_views'] or 0
        
        c.execute("""
            SELECT id, titulo, autor, gostos, visualizacoes 
            FROM protocolos 
            ORDER BY gostos DESC, visualizacoes DESC 
            LIMIT 5
        """)
        mais_populares = [dict(row) for row in c.fetchall()]
        
        c.execute("SELECT disciplinas FROM protocolos")
        todas_disciplinas = []
        for row in c.fetchall():
            disc_list = json.loads(row['disciplinas'])
            todas_disciplinas.extend(disc_list)
        
        from collections import Counter
        disc_counter = Counter(todas_disciplinas)
        por_disciplina = [{"disciplina": k, "count": v} for k, v in disc_counter.most_common()]
        
        c.execute("""
            SELECT id, titulo, autor, data_criacao 
            FROM protocolos 
            ORDER BY data_criacao DESC 
            LIMIT 5
        """)
        ultimos = [dict(row) for row in c.fetchall()]
        
        conn.close()
        
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

# ROTA: Gerar protocolo
@app.route("/generate_protocol", methods=["POST"])
def generate_protocol():
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

# ROTA: Regenerar protocolo
@app.route("/regenerate_protocol", methods=["POST"])
def regenerate_protocol():
    data = request.get_json()
    protocolo_anterior = data.get("protocolo_anterior", {})
    feedback = data.get("feedback", "")
    
    print(f"🔄 A regenerar protocolo com feedback: {feedback[:50]}...")

    protocolo_novo = regenerar_protocolo_ia(protocolo_anterior, feedback)
    
    protocolo_novo["autor"] = protocolo_anterior.get("autor", "")
    protocolo_novo["anos"] = protocolo_anterior.get("anos", [])
    protocolo_novo["disciplinas"] = protocolo_anterior.get("disciplinas", [])

    return jsonify({"status": "ok", "protocolo": protocolo_novo})

# ROTA: Guardar protocolo
@app.route("/save_protocol", methods=["POST"])
def save_protocol():
    data = request.get_json()
    protocolo = data.get("protocolo", {})

    print(f"💾 A guardar protocolo: {protocolo.get('titulo', '(sem título)')}")

    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Preparar dados - converter listas para strings
        seguranca_json = json.dumps(protocolo.get("seguranca", {}))
        quiz_json = json.dumps(protocolo.get("quiz", []))
        diferenciacao_json = json.dumps(protocolo.get("diferenciacao", {}))
        
        # Função auxiliar para converter lista em string
        def to_string(value):
            if isinstance(value, list):
                return "\n".join(str(v) for v in value)
            return str(value) if value else ""
        
        # Converter todos os campos que podem ser listas
        competencias = to_string(protocolo.get("competencias", ""))
        objetivos = to_string(protocolo.get("objetivos", ""))
        recursos_extras = to_string(protocolo.get("recursos_extras", ""))
        
        # Garantir que campos de texto não são listas
        titulo = to_string(protocolo.get("titulo", ""))
        subtitulo = to_string(protocolo.get("subtitulo", ""))
        duracao = to_string(protocolo.get("duracao", ""))
        contextualizacao = to_string(protocolo.get("contextualizacao", ""))
        resumo = to_string(protocolo.get("resumo", ""))
        materiais = to_string(protocolo.get("materiais", ""))
        pre_experiencia = to_string(protocolo.get("pre_experiencia", ""))
        procedimento = to_string(protocolo.get("procedimento", ""))
        pos_experiencia = to_string(protocolo.get("pos_experiencia", ""))
        resultados_esperados = to_string(protocolo.get("resultados_esperados", ""))
        autor = to_string(protocolo.get("autor", ""))
        
        c.execute("""
            INSERT INTO protocolos 
            (titulo, subtitulo, duracao, competencias, objetivos, contextualizacao,
             resumo, materiais, pre_experiencia, procedimento, pos_experiencia,
             resultados_esperados, seguranca_json, quiz_json, diferenciacao_json,
             recursos_extras, disciplinas, anos, autor) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            titulo,
            subtitulo,
            duracao,
            competencias,
            objetivos,
            contextualizacao,
            resumo,
            materiais,
            pre_experiencia,
            procedimento,
            pos_experiencia,
            resultados_esperados,
            seguranca_json,
            quiz_json,
            diferenciacao_json,
            recursos_extras,
            json.dumps(protocolo.get("disciplinas", [])),
            json.dumps(protocolo.get("anos", [])),
            autor
        ))
        conn.commit()
        protocol_id = c.lastrowid
        conn.close()
        print("✅ Protocolo pedagógico guardado!")
        return jsonify({"status": "ok", "id": protocol_id})
    except Exception as e:
        print("❌ Erro ao guardar:", e)
        return jsonify({"status": "erro", "message": str(e)}), 500

@app.route("/search_protocols")
def search_protocols():
    q = request.args.get("q", "")
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM protocolos
        WHERE titulo LIKE ? OR resumo LIKE ? OR autor LIKE ?
        ORDER BY data_criacao DESC
    """, (f"%{q}%", f"%{q}%", f"%{q}%"))
    resultados = [dict(row) for row in c.fetchall()]
    for r in resultados:
        r["disciplinas"] = json.loads(r["disciplinas"])
        r["anos"] = json.loads(r["anos"])
    conn.close()
    return jsonify(resultados)

@app.route("/protocolo/<int:id>")
def ver_protocolo(id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("UPDATE protocolos SET visualizacoes = visualizacoes + 1 WHERE id=?", (id,))
    conn.commit()
    
    c.execute("SELECT * FROM protocolos WHERE id=?", (id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return "Protocolo não encontrado"
    
    protocolo = dict(row)
    protocolo["disciplinas"] = json.loads(protocolo["disciplinas"])
    protocolo["anos"] = json.loads(protocolo["anos"])
    
    # Parse JSON fields
    try:
        protocolo["seguranca"] = json.loads(protocolo.get("seguranca_json", "{}"))
    except:
        protocolo["seguranca"] = {}
    
    try:
        protocolo["quiz"] = json.loads(protocolo.get("quiz_json", "[]"))
    except:
        protocolo["quiz"] = []
    
    try:
        protocolo["diferenciacao"] = json.loads(protocolo.get("diferenciacao_json", "{}"))
    except:
        protocolo["diferenciacao"] = {}
    
    # Gerar QR Code
    qr_code_data = gerar_qr_code(request.host_url + f"protocolo/{id}")
    protocolo["qr_code"] = qr_code_data
    
    return render_template("protocolo.html", protocolo=protocolo)

# ROTA: Avaliar protocolo
@app.route("/avaliar_protocolo/<int:id>", methods=["POST"])
def avaliar_protocolo(id):
    data = request.get_json()
    tipo = data.get("tipo")
    
    if tipo not in ['gosto', 'nao_gosto']:
        return jsonify({"status": "erro", "message": "Tipo inválido"}), 400
    
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        if tipo == 'gosto':
            c.execute("UPDATE protocolos SET gostos = gostos + 1 WHERE id=?", (id,))
        else:
            c.execute("UPDATE protocolos SET nao_gostos = nao_gostos + 1 WHERE id=?", (id,))
        
        conn.commit()
        
        c.execute("SELECT gostos, nao_gostos FROM protocolos WHERE id=?", (id,))
        row = c.fetchone()
        conn.close()
        
        return jsonify({
            "status": "ok",
            "gostos": row[0],
            "nao_gostos": row[1]
        })
    except Exception as e:
        print(f"❌ Erro ao avaliar: {e}")
        return jsonify({"status": "erro", "message": str(e)}), 500

# ----------------- FUNÇÕES AUXILIARES -----------------
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

# ----------------- FUNÇÕES IA -----------------
def gerar_protocolo_ia(titulo, resumo, anos, disciplinas):
    """Gera protocolo experimental PEDAGÓGICO COMPLETO"""
    
    prompt = f"""És um especialista em EDUCAÇÃO EM CIÊNCIAS com experiência em pedagogia das ciências experimentais, currículo português do ensino básico e segurança em laboratório escolar.

Cria um protocolo experimental COMPLETO, PEDAGÓGICO e SEGURO em português de Portugal.

INFORMAÇÃO BASE:
- Título: {titulo}
- Descrição: {resumo}
- Anos letivos: {', '.join(anos)}
- Disciplinas: {', '.join(disciplinas)}

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

IMPORTANTE: Linguagem adequada aos anos {', '.join(anos)}. Segurança é PRIORITÁRIA."""

    try:
        print("🤖 A gerar protocolo pedagógico completo...")
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "És um especialista em educação em ciências. Crias protocolos pedagógicos completos, seguros e alinhados com o currículo português. Respondes SEMPRE em JSON válido."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=3500
        )
        
        resposta_texto = response.choices[0].message.content
        print("📥 Resposta recebida do Groq")
        
        # Limpar markdown
        resposta_texto = resposta_texto.strip()
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

def criar_protocolo_fallback(titulo, resumo):
    """Protocolo básico em caso de erro"""
    return {
        "titulo": titulo,
        "subtitulo": "Protocolo experimental",
        "duracao": "45 minutos",
        "competencias": ["Trabalho prático"],
        "objetivos": ["Realizar a experiência proposta"],
        "contextualizacao": resumo,
        "resumo": resumo,
        "materiais": "Erro ao gerar materiais. Por favor, tenta novamente.",
        "pre_experiencia": "Discussão prévia sobre o tema.",
        "procedimento": "Erro ao gerar procedimento. Por favor, tenta novamente.",
        "pos_experiencia": "Discussão dos resultados observados.",
        "resultados_esperados": "A definir.",
        "seguranca": {
            "nivel_risco": "Médio",
            "riscos": "Análise de segurança não disponível.",
            "epi": "Óculos e bata de laboratório recomendados.",
            "supervisao": "Professor presente.",
            "cuidados": "Supervisão constante necessária.",
            "primeiros_socorros": "Contactar responsável em caso de acidente.",
            "descarte": "Seguir normas do laboratório."
        },
        "quiz": [],
        "diferenciacao": {
            "simplificacao": [],
            "aprofundamento": [],
            "inclusao": []
        },
        "recursos_extras": []
    }

def regenerar_protocolo_ia(protocolo_anterior, feedback):
    """Regenera protocolo com feedback"""
    prompt = f"""Melhora este protocolo experimental com base no feedback do utilizador.

PROTOCOLO ANTERIOR:
{json.dumps(protocolo_anterior, indent=2, ensure_ascii=False)}

FEEDBACK:
{feedback}

INSTRUÇÕES:
- Mantém a estrutura JSON completa
- Melhora apenas o que foi pedido
- Mantém segurança e qualidade pedagógica
- Responde APENAS com JSON, sem markdown

Retorna o protocolo melhorado no mesmo formato JSON."""

    try:
        print("🔄 A regenerar protocolo...")
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "És um especialista em melhorar protocolos experimentais. Respondes em JSON válido."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=3500
        )
        
        resposta_texto = response.choices[0].message.content.strip()
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

# ----------------- MAIN -----------------
if __name__ == "__main__":
    criar_base_de_dados()
    print("🚀 A iniciar servidor Flask com PROMPTS PEDAGÓGICOS MELHORADOS...")
    print("📍 Acede a: http://127.0.0.1:5000")
    
    # Configuração para Render (usa porta do ambiente)
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
```

**Guarda o ficheiro!**

---

## ✅ **RESUMO DAS ALTERAÇÕES:**

Fizeste 3 pequenas correções:

1. ✅ `requirements.txt` → Adicionaste `Pillow`
2. ✅ `.gitignore` → Adicionaste `*.db`
3. ✅ `app.py` → Final corrigido para Render

---

## 📁 **FICHEIRO 6: Templates**

Confirma que tens estes 4 ficheiros na pasta `templates/`:
```
templates/
├── index.html
├── gerar_protocolo.html
├── consultar_protocolos.html
└── protocolo.html