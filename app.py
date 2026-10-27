import streamlit as st
import pandas as pd
import psycopg2
import os
import re
import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Controle de Estoque - Aços Vital", layout="wide")

# --- OCULTAR ELEMENTOS INDESEJADOS ---
esconder_elementos = """
    <style>
    /* Esconde a marca d'água do Streamlit no rodapé */
    footer {visibility: hidden !important;}
    
    /* Esconde o botão de Deploy na barra superior */
    .stAppDeployButton {display: none !important;}
    
    /* Esconde apenas os links (ícone do GitHub) dentro da barra superior, mantendo os 3 pontinhos */
    [data-testid="stToolbar"] a {display: none !important;}
    </style>
    """
st.markdown(esconder_elementos, unsafe_allow_html=True)

# --- GPS DA IMAGEM ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
caminho_png = os.path.join(BASE_DIR, "logo.png")
caminho_jpg = os.path.join(BASE_DIR, "logo.jpg")

if os.path.exists(caminho_png):
    logo_path = caminho_png
elif os.path.exists(caminho_jpg):
    logo_path = caminho_jpg
else:
    logo_path = None

# ==========================================
# SISTEMA DE LOGIN E SEGURANÇA
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'perfil' not in st.session_state:
    st.session_state['perfil'] = ''
if 'usuario_nome' not in st.session_state:
    st.session_state['usuario_nome'] = ''

if not st.session_state['logged_in']:
    col1, col2, col3 = st.columns([1.5, 1, 1.5]) 
    with col2:
        if logo_path:
            st.image(logo_path, use_container_width=True)
        else:
            st.warning("⚠️ Imagem não encontrada. Certifique-se de que o nome é 'logo' e está na mesma pasta.")
            
        st.markdown("<h3 style='text-align: center;'>🔐 Acesso ao Sistema</h3>", unsafe_allow_html=True)
        usuario = st.text_input("Usuário").strip().lower()
        senha = st.text_input("Senha", type="password")
        btn_login = st.button("Entrar", use_container_width=True, type="primary")

        # --- DICIONÁRIO DE USUÁRIOS E SENHAS ---
        usuarios_pcp = {
            "denis.pcp": "Davi&Heitor",
            "joao.pcp": "46993061",
            "jonathan.pcp": "120910",
            "Pedro.stock": "014775",
            "douglas.mogi": "drowssap",
            "entrada.mogi": "adartnedrowssap",
            "saida.mogi": "adiasdrowssap"
        }

        usuarios_vendas = {
            "vendas": "AcosVital@2026",
            "compras": "AV@2026"
        }

        # Mapeamento de nomes amigáveis para o Log de Auditoria
        nomes_exibicao = {
            "denis.pcp": "Denis",
            "joao.pcp": "João V.",
            "jonathan.pcp": "Jonathan",
            "Pedro.stock": "Pedro (URA)",
            "douglas.mogi": "Douglas (MOGI)",
            "entrada.mogi": "Entrada (MOGI)",
            "saida.mogi": "Saida (MOGI)",
            "vendas": "Vendas",
            "compras": "Compras"
        }

        if btn_login:
            if usuario in usuarios_pcp and senha == usuarios_pcp[usuario]:
                st.session_state['logged_in'] = True
                st.session_state['perfil'] = "PCP"
                st.session_state['usuario_nome'] = nomes_exibicao.get(usuario, usuario)
                st.rerun()
            elif usuario in usuarios_vendas and senha == usuarios_vendas[usuario]:
                st.session_state['logged_in'] = True
                st.session_state['perfil'] = "VENDEDOR"
                st.session_state['usuario_nome'] = nomes_exibicao.get(usuario, usuario)
                st.rerun()
            else:
                st.error("❌ Usuário ou senha incorretos!")
    
    st.stop()

# ==========================================
# BARRA LATERAL (MENU E LOGOUT)
# ==========================================
if logo_path:
    st.sidebar.image(logo_path, use_container_width=True)

st.sidebar.markdown(f"**👤 Operador:** {st.session_state['usuario_nome']}")
st.sidebar.markdown(f"**💼 Perfil:** {st.session_state['perfil']}")
st.sidebar.markdown("---")
if st.sidebar.button("🚪 Sair do Sistema", use_container_width=True):
    st.session_state['logged_in'] = False
    st.session_state['perfil'] = ''
    st.session_state['usuario_nome'] = ''
    st.rerun()

# ==========================================
# BANCO DE DADOS NA NUVEM (SUPABASE)
# ==========================================
st.title("📦 Sistema de Controle de Estoque")
st.markdown("---")

DATABASE_URL = st.secrets["DATABASE_URL"]

@st.cache_resource(ttl=600) # Pede para o site reciclar a conexão a cada 10 minutos
def init_connection():
    return psycopg2.connect(DATABASE_URL)

conn = init_connection()

# Sistema de auto-cura: Se o Supabase tiver derrubado a conexão, ele reconecta sozinho
try:
    conn.rollback() 
except psycopg2.InterfaceError:
    st.cache_resource.clear() # Limpa a memória velha
    conn = init_connection()  # Abre uma conexão nova
    conn.rollback()           # Roda a Chave Mestra
    
c = conn.cursor()

# Criação da tabela base de materiais (Exatamente como no app_2.py)
c.execute('''
    CREATE TABLE IF NOT EXISTS materiais (
        id SERIAL PRIMARY KEY,
        codigo TEXT,
        categoria TEXT,
        tipo TEXT,
        nome TEXT,
        dimensoes TEXT,
        unidade TEXT,
        saldo REAL,
        filial TEXT,
        valor_kg TEXT,
        origem TEXT,
        st TEXT,
        difal TEXT,
        icms TEXT
    )
''')

# Criação da tabela de histórico (Log de Auditoria)
c.execute('''
    CREATE TABLE IF NOT EXISTS historico_movimentacao (
        id SERIAL PRIMARY KEY,
        data_hora TIMESTAMP,
        usuario TEXT,
        categoria TEXT,
        tipo TEXT,
        nome TEXT,
        dimensoes TEXT,
        unidade TEXT,
        operacao TEXT,
        quantidade REAL
    )
''')
conn.commit()

# Migração automática de novas colunas fiscais e de origem para itens antigos
try:
    c.execute("ALTER TABLE materiais ADD COLUMN IF NOT EXISTS codigo TEXT;")
    c.execute("ALTER TABLE materiais ADD COLUMN IF NOT EXISTS filial TEXT;")
    c.execute("ALTER TABLE materiais ADD COLUMN IF NOT EXISTS valor_kg TEXT;")
    c.execute("ALTER TABLE materiais ADD COLUMN IF NOT EXISTS origem TEXT;")
    c.execute("ALTER TABLE materiais ADD COLUMN IF NOT EXISTS st TEXT;")
    c.execute("ALTER TABLE materiais ADD COLUMN IF NOT EXISTS difal TEXT;")
    c.execute("ALTER TABLE materiais ADD COLUMN IF NOT EXISTS icms TEXT;")
    
    c.execute("UPDATE materiais SET origem = '' WHERE origem IS NULL OR origem = '-'")
    c.execute("UPDATE materiais SET st = '' WHERE st IS NULL OR st = '-'")
    c.execute("UPDATE materiais SET difal = '' WHERE difal IS NULL OR difal = '-'")
    c.execute("UPDATE materiais SET icms = '' WHERE icms IS NULL OR icms = '-'")
    conn.commit()
except:
    conn.rollback()

# --- FUNÇÃO AUXILIAR: FUSO HORÁRIO DE BRASÍLIA ---
def obter_agora_br():
    return datetime.datetime.utcnow() - datetime.timedelta(hours=3)

# --- FUNÇÃO AUXILIAR: FORMATAR COLUNA UNIFICADA "ST (%) | DIFAL (%) | ICMS (%)" ---
def formatar_tributacao_unificada(r):
    partes = []
    st_v = str(r.get('st', '')).strip()
    dif_v = str(r.get('difal', '')).strip()
    icm_v = str(r.get('icms', '')).strip()
    
    if st_v not in ["", "-", "None"]:
        partes.append(f"ST: {st_v}%")
    if dif_v not in ["", "-", "None"]:
        partes.append(f"DIFAL: {dif_v}%")
    if icm_v not in ["", "-", "None"]:
        partes.append(f"ICMS: {icm_v}%")
    return " | ".join(partes)

def extrair_impostos_da_coluna(texto_trib, st_atual, difal_atual, icms_atual):
    texto = str(texto_trib).strip().upper()
    if not texto or texto == "-":
        return "", "", ""
    
    m_st = re.search(r'ST\s*:?\s*([0-9,]+)', texto)
    m_dif = re.search(r'DIFAL\s*:?\s*([0-9,]+)', texto)
    m_icm = re.search(r'ICMS\s*:?\s*([0-9,]+)', texto)
    
    if m_st or m_dif or m_icm:
        novo_st = m_st.group(1) if m_st else ""
        novo_dif = m_dif.group(1) if m_dif else ""
        novo_icm = m_icm.group(1) if m_icm else ""
        return novo_st, novo_dif, novo_icm
        
    # Caso o operador digite apenas números separados por "|" (Ex: 18 | 6 | 12)
    partes = [re.sub(r'[^0-9,]', '', p) for p in texto.split("|")]
    if len(partes) == 3:
        return partes[0], partes[1], partes[2]
    elif len(partes) == 1 and partes[0]:
        return partes[0], difal_atual, icms_atual
    return st_atual, difal_atual, icms_atual

# --- FUNÇÃO AUXILIAR: FORMATADOR DE IDENTIFICADOR ---
def montar_identificador(r):
    cod_str = f"[{r['codigo']}] " if str(r['codigo']) not in ["-", "", "None"] else ""
    val_str = f" | R$ {r['valor_kg']}/kg" if str(r['valor_kg']) not in ["-", "", "None"] else ""
    
    extras = []
    if str(r.get('origem', '')).strip() not in ["", "-", "None"]:
        extras.append(f"Orig: {r['origem']}")
        
    trib_str = formatar_tributacao_unificada(r)
    if trib_str:
        extras.append(trib_str)
        
    fiscal_str = " | " + " | ".join(extras) if extras else ""
    return f"{cod_str}{r['nome']} - {r['dimensoes']} | {r['filial']} | Saldo: {int(r['saldo'])} {r['unidade']}{val_str}{fiscal_str}"

# --- FUNÇÃO AUXILIAR: EXIBIÇÃO DO HISTÓRICO NAS ABAS ---
def exibir_historico_operacoes():
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("⏱️ Histórico de Confirmação de Ações Recentes")
    
    c.execute('''
        SELECT data_hora, usuario, categoria, nome, dimensoes, unidade, operacao, quantidade 
        FROM historico_movimentacao 
        ORDER BY data_hora DESC LIMIT 15
    ''')
    logs = c.fetchall()
    
    if not logs:
        st.info("Nenhum registo de atividade encontrado no sistema.")
    else:
        df_logs = pd.DataFrame(logs, columns=["Data_Hora_Raw", "Quem fez a movimentação", "Categoria", "Tipo", "Dimensões", "UNID", "Entrada/Saida", "Quantidade"])
        
        df_logs['Data da movimentação'] = pd.to_datetime(df_logs['Data_Hora_Raw']).dt.strftime('%d/%m/%Y')
        df_logs['Horas da movimentação'] = pd.to_datetime(df_logs['Data_Hora_Raw']).dt.strftime('%H:%M')
        
        df_final_logs = df_logs[[
            "Data da movimentação", "Horas da movimentação", "Quem fez a movimentação", 
            "Categoria", "Tipo", "Dimensões", "UNID", "Entrada/Saida", "Quantidade"
        ]]
        
        st.dataframe(df_final_logs, use_container_width=True, hide_index=True)

# --- LÓGICA DE EXIBIÇÃO POR PERFIL ---

if st.session_state['perfil'] == "PCP":
    aba_cadastro, aba_movimentacao, aba_inventario = st.tabs(["➕ Cadastrar Material", "🔄 Movimentação", "📋 Inventário"])

    with aba_cadastro:
        st.subheader("➕ Cadastrar Novo Material")

        categorias_catalogo = {
            "FLANGES": ["ANSI", "AWWA C-207", "PN"],
            "CONEXÕES": ["Curva", "Cruz (ASME B16.9 ou Inox MSS SP-43)", "Redução (ASME B16.9 ou Inox MSS SP-43)", "Pestana (ASME B16.9 ou Inox MSS SP-43)", "Niple de Redução (ASME B16.9 ou MSSP-95)", "Alta Pressão / Forjadas", "Colares", "Plugs / Buchas / Niples"],
            "TUBOS": ["Aço Inox", "Com Costura", "Aço Carbono", "Mecânicos Laminados", "Calandrados de Grandes Diâmetros", "Industriais"],
            "VÁLVULAS": ["Válvula Esfera", "Válvula Gaveta", "Válvula Borboleta", "Válvula Retenção Dupla Portinhola", "Válvula Globo", "Válvula Guilhotina"],
            "LINHA PEAD": ["Flange Solto PEAD", "Conexões de Eletrofusão", "Conexões Injetadas", "Colarinhos Usinados", "Curvas", "Tees Segmentadas", "Redução Usinada"],
            "PERFIS LAMINADOS E DOBRADOS": ["Perfil (W) / I", "Perfil U", "Cantoneira", "Barra"],
            "CHAPAS E GRADES": ["Fina Frio", "Fina Quente", "Inox", "Grossa", "Xadrez", "Zincada", "Perfurada - Furo Redondo", "Expandida", "Piso Soldadas", "Piso Entrelaçadas", "Degraus para Escadas"],
            "CONSTRUÇÃO CIVIL": ["Vergalhões CA - 25", "Vergalhões CA - 50", "Vergalhões CA - 60", "Arame Recozido", "Barra de Transferência", "Tela Soldada Nervurada", "Telha", "Treliça"]
        }

        col1, col2 = st.columns(2)
        with col1:
            categoria = st.selectbox("Categoria", list(categorias_catalogo.keys()), key="cad_cat_principal")
        with col2:
            tipo = st.selectbox("Tipo", categorias_catalogo[categoria], key="cad_tipo_principal")
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        # ==========================================
        # VACINA 3: Espelho do Catálogo Inteligente
        # ==========================================
        if tipo == "Cantoneira":
            c.execute("SELECT codigo, nome, dimensoes, filial FROM materiais WHERE categoria = %s AND (tipo LIKE 'Cantoneira%%' OR nome LIKE 'CANTONEIRA%%') ORDER BY nome, dimensoes", (categoria,))
        elif tipo == "Perfil (W) / I":
            c.execute("SELECT codigo, nome, dimensoes, filial FROM materiais WHERE categoria = %s AND (tipo IN ('Perfil (W) / I', '(W) I', '(W) H - HP', 'I - Abas Inclinadas') OR nome LIKE 'PERFIL (W)%%' OR nome LIKE 'PERFIL W%%' OR nome LIKE 'PERFIL HP%%' OR nome LIKE 'PERFIL I%%') ORDER BY nome, dimensoes", (categoria,))
        elif tipo == "Perfil U":
            c.execute("SELECT codigo, nome, dimensoes, filial FROM materiais WHERE categoria = %s AND (tipo LIKE 'U -%%' OR tipo = 'Perfil U' OR nome LIKE 'PERFIL U%%') ORDER BY nome, dimensoes", (categoria,))
        elif tipo == "Barra":
            c.execute("SELECT codigo, nome, dimensoes, filial FROM materiais WHERE categoria = %s AND (tipo LIKE 'Barra%%' OR nome LIKE 'BARRA%%') ORDER BY nome, dimensoes", (categoria,))
        else:
            c.execute("SELECT codigo, nome, dimensoes, filial FROM materiais WHERE categoria = %s AND tipo = %s ORDER BY nome, dimensoes", (categoria, tipo))
            
        catalogo_existente = c.fetchall()
        if catalogo_existente:
            with st.expander(f"👀 Ver peças do grupo '{tipo}' já cadastradas (Evite duplicidade!)", expanded=True):
                df_cat = pd.DataFrame(catalogo_existente, columns=["Código", "Tipo / Nome", "Dimensões", "Filial"])
                st.dataframe(df_cat, use_container_width=True, hide_index=True)
        
        st.markdown("<br>", unsafe_allow_html=True)

        # --- CABEÇALHO GERAL DO MATERIAL E TRIBUTAÇÃO ---
        col_cod, col_filial, col_valor = st.columns([1.5, 1, 1])
        codigo_em_uso = False # Trava mestre
        
        with col_cod:
            codigo = st.text_input("Código do Material (Opcional)", key="cad_codigo")
            if codigo:
                codigo_limpo = codigo.strip().upper()
                c.execute("SELECT nome, dimensoes FROM materiais WHERE UPPER(codigo) = %s", (codigo_limpo,))
                registro_existente = c.fetchone()
                if registro_existente:
                    st.error(f"🚫 CÓDIGO EM USO: Já cadastrado em {registro_existente[0]} ({registro_existente[1]}).")
                    codigo_em_uso = True
        with col_filial:
            filial_selecionada = st.selectbox("Aços Vital (Filial)", ["SP", "MG"], key="cad_filial")
        with col_valor:
            valor_kg = st.text_input("Valor / kg (R$)", help="Ex: 15,50", key="cad_valor_kg")

        st.markdown("**🌐 Origem e Tributação (Opcional - Preencha apenas se aplicável)**")
        col_orig_sel, col_orig_pct, col_st, col_difal, col_icms = st.columns([1.2, 1, 1, 1, 1])
        with col_orig_sel:
            origem_tipo = st.selectbox("Origem", ["Não informar", "Nacional", "Importado"], key="cad_orig_tipo")
        with col_orig_pct:
            origem_pct = st.text_input("Alíq. Origem (%)", help="Ex: 4 ou 12 (Opcional)", key="cad_orig_pct")
        with col_st:
            st_val = st.text_input("ST (%)", help="Ex: 18 (Apenas números e vírgula)", key="cad_st")
        with col_difal:
            difal_val = st.text_input("DIFAL (%)", help="Ex: 6 (Apenas números e vírgula)", key="cad_difal")
        with col_icms:
            icms_val = st.text_input("ICMS (%)", help="Ex: 18 (Apenas números e vírgula)", key="cad_icms")

        st.markdown("<hr style='margin-top: 5px; margin-bottom: 20px;'>", unsafe_allow_html=True)
                    
        nome = ""
        dimensoes_para_salvar = ""
        unidade_para_salvar = "UNID" 
        campos_vazios = False 

        if categoria == "FLANGES":
            if tipo == "ANSI":
                col3, col4, col5 = st.columns(3)
                with col3:
                    classe = st.selectbox("Classe", ["150 LBS", "300 LBS", "400 LBS", "600 LBS", "900 LBS", "1500 LBS"], key="cad_classe_ansi")
                with col4:
                    modelo = st.selectbox("Modelo", ["WN (Weld-Neck)", "SW (Socket-Weld)", "CEGO", "SOB PLANO", "SO (Slip-on)", "SOLTO"], key="cad_modelo_ansi")
                with col5:
                    dimensao_valor = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_ansi")
                        
                nome = f"{classe} {modelo}"
                dimensao_limpa = dimensao_valor.replace('"', '').strip()
                dimensoes_para_salvar = f'{dimensao_limpa}"' if dimensao_limpa else ""
                if not dimensao_valor: campos_vazios = True

            elif tipo == "AWWA C-207":
                col3, col4 = st.columns(2)
                with col3:
                    opcoes_awwa = ["Classe B (86 psi)", "Classe D (175 : 150 psi)", "Classe E (275 psi)", "Classe F (300 psi)"]
                    classe = st.selectbox("Classe e Pressão", opcoes_awwa, key="cad_classe_awwa")
                with col4:
                    dimensao_valor = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_awwa")
                    
                nome = f"{classe}"
                dimensao_limpa = dimensao_valor.replace('"', '').strip()
                dimensoes_para_salvar = f'{dimensao_limpa}"' if dimensao_limpa else ""
                if not dimensao_valor: campos_vazios = True

            elif tipo == "PN":
                col3, col4, col5 = st.columns(3)
                with col3:
                    pn_valor = st.selectbox("Pressão (PN)", ["10", "16", "25", "40", "63", "100"], key="cad_pn_val")
                with col4:
                    classe_pn = st.selectbox("Classe", ["Tipo 1", "Tipo 2", "Tipo 5", "Tipo 11", "Tipo 12"], key="cad_classe_pn")
                with col5:
                    dimensao_valor = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_pn")
                    
                nome = f"PN {pn_valor} {classe_pn}"
                dimensao_limpa = dimensao_valor.replace('"', '').strip()
                dimensoes_para_salvar = f'{dimensao_limpa}"' if dimensao_limpa else ""
                if not dimensao_valor: campos_vazios = True

        elif categoria == "CONEXÕES":
            if tipo == "Curva":
                col3, col4, col5 = st.columns(3)
                with col3:
                    modelo_curva = st.selectbox("Modelo", ["Curva 45°", "Curva 90°", "Curva 180°", "Curva outro °"], key="cad_mod_curva")
                    if modelo_curva == "Curva outro °":
                        grau_custom = st.text_input("Qual o Grau?", key="cad_grau_curva")
                        nome = f"Curva {grau_custom}°" if grau_custom else "Curva"
                    else:
                        nome = modelo_curva
                        grau_custom = "N/A"
                with col4:
                    dim_nom = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_curva")
                with col5:
                    schedule = st.text_input("Schedule (Opcional)", key="cad_sch_curva")
                    
                dimensao_limpa = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dimensao_limpa}"' if dimensao_limpa else ""
                if schedule: dimensoes_para_salvar = f"SCH {schedule.upper()} | " + dimensoes_para_salvar
                if not dim_nom or (modelo_curva == "Curva outro °" and not grau_custom): campos_vazios = True

            elif tipo == "Cruz (ASME B16.9 ou Inox MSS SP-43)":
                col3, col4, col5 = st.columns(3)
                with col3:
                    nome = st.selectbox("Modelo", ["Te", "Cruzeta", "CAP"], key="cad_mod_cruz")
                with col4:
                    dim_nom = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_cruz")
                with col5:
                    schedule = st.text_input("Schedule (Opcional)", key="cad_sch_cruz")
                    
                dimensao_limpa = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dimensao_limpa}"' if dimensao_limpa else ""
                if schedule: dimensoes_para_salvar = f"SCH {schedule.upper()} | " + dimensoes_para_salvar
                if not dim_nom: campos_vazios = True

            elif tipo in ["Redução (ASME B16.9 ou Inox MSS SP-43)", "Niple de Redução (ASME B16.9 ou MSSP-95)"]:
                col3, col4, col5 = st.columns(3)
                with col3:
                    modelo = st.selectbox("Modelo", ["Concêntrica", "Excêntrica"], key=f"cad_mod_{tipo[:3]}")
                with col4:
                    dim_nom = st.text_input("Diâm. Nom. (Pol)", key=f"cad_dim1_{tipo[:3]}")
                with col5:
                    dim_red = st.text_input("Diâm. Red. (Pol)", key=f"cad_dim2_{tipo[:3]}")
                    
                col6, col7 = st.columns(2)
                with col6:
                    comp = st.text_input("Comprimento (mm)", key=f"cad_comp_{tipo[:3]}")
                with col7:
                    schedule = st.text_input("Schedule (Opcional)", key=f"cad_sch_{tipo[:3]}")
                    
                nome_base = "Redução" if "Redução" in tipo and "Niple" not in tipo else "Niple de Redução"
                nome = f"{nome_base} {modelo}"
                dim1 = dim_nom.replace('"', '').strip()
                dim2 = dim_red.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}" x {dim2}" | Comp: {comp}mm'
                if schedule: dimensoes_para_salvar = f"SCH {schedule.upper()} | " + dimensoes_para_salvar
                if not dim_nom or not dim_red or not comp: campos_vazios = True

            elif tipo == "Pestana (ASME B16.9 ou Inox MSS SP-43)":
                col3, col4 = st.columns(2)
                with col3:
                    modelo = st.selectbox("Modelo", ["ANSI Curto", "ANSI Longo", "MSS Tipo A", "MSS Tipo B"], key="cad_mod_pest")
                    dim_garg = st.text_input("Diâm. Garganta (mm)", key="cad_dim2_pest")
                with col4:
                    dim_nom = st.text_input("Diâm. Nom. (Pol)", key="cad_dim1_pest")    
                    comp = st.text_input("Comprimento (mm)", key="cad_comp_pest")
                    
                nome = f"Pestana {modelo}"
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}" | Garg: {dim_garg}mm | Comp: {comp}mm'
                if not dim_nom or not dim_garg or not comp: campos_vazios = True

            elif tipo == "Alta Pressão / Forjadas":
                col3, col4, col5 = st.columns(3)
                with col3:
                    modelo = st.selectbox("Modelo", ["Cotovelo 45°", "Cotovelo 90°", "Te", "Cruzeta", "Luva", "Meia Luva", "CAP Roscado"], key="cad_mod_alta")
                with col4:
                    classe = st.selectbox("Classe", ["Nenhum", "3000#", "6000#", "9000#"], key="cad_cla_alta")
                with col5:
                    dim_nom = st.text_input("Diâm. Nom. (Pol)", key="cad_dim1_alta")
                    
                dim_tubo = st.text_input("Diâm. Tubo (Pol) - Opcional", key="cad_dim2_alta")
                    
                nome = f"{modelo} {classe}"
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}"'
                if dim_tubo: 
                    dim2 = dim_tubo.replace('"', '').strip()
                    dimensoes_para_salvar += f' x {dim2}"'
                if not dim_nom: campos_vazios = True

            elif tipo == "Colares":
                col3, col4 = st.columns(2)
                with col3:
                    modelo = st.selectbox("Modelo", ["Colar BW", "Colar BW Weldolet", "Colar TH Roscado", "Sockolet Colar SW"], key="cad_mod_colar")
                with col4:
                    classe = st.selectbox("Classe", ["3000#", "6000#", "9000#"], key="cad_cla_colar")
                    
                dim_nom = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_colar")
                nome = f"{modelo} {classe}"
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}"'
                if not dim_nom: campos_vazios = True

            elif tipo == "Plugs / Buchas / Niples":
                col3, col4 = st.columns(2)
                with col3:
                    nome = st.selectbox("Modelo", ["Bucha de Redução", "Bucha de Redução Sextavada", "Niple Duplo", "Plug Cabeça Quadrada", "Plug Cabeça Sextavada", "Plug Cabeça Redonda"], key="cad_mod_plug")
                with col4:
                    dim_nom = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_plug")
                    
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}"'
                if not dim_nom: campos_vazios = True

        elif categoria == "TUBOS":
            modelos_tubos = {
                "Aço Inox": ["5-S", "10-S", "20-S", "40-S", "80-S", "160-S"],
                "Com Costura": ["Leve", "Média", "Pesada"],
                "Aço Carbono": ["Nenhum","SCH 10", "SCH 20", "SCH 30", "SCH 40", "SCH 60", "SCH 80", "SCH 100", "SCH 120", "SCH 140", "SCH 160"],
                "Mecânicos Laminados": ["Com Centragem Externa", "Com Centragem Interna"],
                "Industriais": ["Redondos", "Quadrados", "Retangulares"],
                "Calandrados de Grandes Diâmetros": []
            }
            
            lista_modelos = modelos_tubos[tipo]
            
            if tipo == "Industriais":
                modelo = st.selectbox("Especificação", lista_modelos, key="cad_mod_tubo")
                
                if modelo == "Quadrados":
                    col3, col4, col5 = st.columns(3)
                    with col3:
                        bitola = st.text_input("Bitola (mm)", key="cad_bit_quad")
                    with col4:
                        espessura = st.text_input("Espessura (mm)", key="cad_esp_quad")
                    with col5:
                        tamanho = st.selectbox("Tamanho", ["UNID/6", "UNID/12"], key="cad_tam_quad")
                    nome = f"Tubo {tipo} {modelo}"
                    dimensoes_para_salvar = f"Bitola: {bitola}mm | Esp: {espessura}mm"
                    unidade_para_salvar = tamanho
                    if not bitola or not espessura: campos_vazios = True
                    
                elif modelo == "Retangulares":
                    col3, col4, col5, col6 = st.columns(4)
                    with col3:
                        bitola_l = st.text_input("Bitola l (mm)", key="cad_bitl_ret")
                    with col4:
                        bitola_c = st.text_input("Bitola c (mm)", key="cad_bitc_ret")
                    with col5:
                        espessura = st.text_input("Espessura (mm)", key="cad_esp_ret")
                    with col6:
                        tamanho = st.selectbox("Tamanho", ["UNID/6", "UNID/12"], key="cad_tam_ret")
                    nome = f"Tubo {tipo} {modelo}"
                    dimensoes_para_salvar = f"Bitola: {bitola_l}x{bitola_c}mm | Esp: {espessura}mm"
                    unidade_para_salvar = tamanho
                    if not bitola_l or not bitola_c or not espessura: campos_vazios = True
                    
                else: 
                    col3, col4, col5 = st.columns(3)
                    with col3:
                        dim_nom = st.text_input("Diâm. Nom. (Pol)", key="cad_dim1_tubo")
                    with col4:
                        espessura = st.text_input("Espessura (mm)", key="cad_dim2_tubo")
                    with col5:
                        tamanho = st.selectbox("Tamanho", ["UNID/6", "UNID/12"], key="cad_tam_tubo")
                    nome = f"Tubo {tipo} {modelo}"
                    dim1 = dim_nom.replace('"', '').strip()
                    dimensoes_para_salvar = f'{dim1}" | Esp: {espessura}mm'
                    unidade_para_salvar = tamanho
                    if not dim_nom or not espessura: campos_vazios = True

            elif lista_modelos:
                col3, col4, col5, col6 = st.columns([2, 1, 1, 1.5])
                with col3:
                    modelo = st.selectbox("Especificação", lista_modelos, key="cad_mod_tubo")
                with col4:
                    dim_nom = st.text_input("Diâm. Nom. (Pol)", key="cad_dim1_tubo")
                with col5:
                    espessura = st.text_input("Espessura (mm)", key="cad_dim2_tubo")
                with col6:
                    tamanho = st.selectbox("Tamanho", ["UNID/6", "UNID/12"], key="cad_tam_tubo")
                    
                nome = f"Tubo {tipo}"
                dim1 = dim_nom.replace('"', '').strip()
                if modelo and modelo != "Nenhum":
                    dimensoes_para_salvar = f'{modelo} | {dim1}" | Esp: {espessura}mm'
                else:
                    dimensoes_para_salvar = f'{dim1}" | Esp: {espessura}mm'
                unidade_para_salvar = tamanho
                if not dim_nom or not espessura: campos_vazios = True
                
            else: 
                col3, col4, col5 = st.columns([1, 1, 1.5])
                with col3:
                    dim_nom = st.text_input("Diâm. Nom. (Pol)", key="cad_dim1_tubo")
                with col4:
                    espessura = st.text_input("Espessura (mm)", key="cad_dim2_tubo")
                with col5:
                    tamanho = st.selectbox("Tamanho", ["UNID/6", "UNID/12"], key="cad_tam_tubo")
                    
                nome = f"Tubo {tipo}"
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}" | Esp: {espessura}mm'
                unidade_para_salvar = tamanho
                if not dim_nom or not espessura: campos_vazios = True

        # --- NOVA CATEGORIA: VÁLVULAS ---
        elif categoria == "VÁLVULAS":
            col3, col4, col5 = st.columns([1.2, 1, 2])
            with col3:
                mat_valvula = st.selectbox("Material do Corpo", ["Aço Carbono", "Inox", "PVC"], key="cad_mat_valv")
            with col4:
                bitola_valv = st.text_input("Bitola (Pol.)", key="cad_bit_valv")
            with col5:
                obs_valv = st.text_input("Observação Livre (Ex: 150 LBS, PN16 - Opcional)", key="cad_obs_valv")
                
            nome = f"{tipo} {mat_valvula}"
            dim1 = bitola_valv.replace('"', '').strip()
            dimensoes_para_salvar = f'Bitola: {dim1}"' if dim1 else ""
            if obs_valv and obs_valv.strip():
                dimensoes_para_salvar += f" | {obs_valv.strip()}"
            unidade_para_salvar = "UNID"
            if not bitola_valv: campos_vazios = True

        elif categoria == "LINHA PEAD":
            if tipo == "Flange Solto PEAD":
                col3, col4 = st.columns(2)
                with col3:
                    opcoes_flange = ["PN 10", "PN 16", "PN 25", "AWWA C-207 TAB.2", "AWWA C-207 TAB.6", "150 LBS", "300 LBS"]
                    modelo = st.selectbox("Modelo / Classe", opcoes_flange, key="cad_mod_pead_flange")
                with col4:
                    dim_nom = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_pead_flange")
                    
                nome = f"{tipo} {modelo}"
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}"'
                if not dim_nom: campos_vazios = True
                
            else:
                col3, col4 = st.columns(2)
                with col3:
                    dim_nom = st.text_input("Diâmetro (Pol)", key="cad_dim_pead_geral")
                with col4:
                    classe_sdr = st.text_input("SDR / PN / Espessura (Opcional)", key="cad_sdr_pead_geral")
                    
                nome = f"{tipo}"
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}"' if dim1 else ""
                if classe_sdr: dimensoes_para_salvar += f" | Classe: {classe_sdr.upper()}"
                if not dim_nom: campos_vazios = True

        elif categoria == "PERFIS LAMINADOS E DOBRADOS":
            tamanho_opcoes = ["UNID/6", "UNID/12"]

            # 1. GRUPO PERFIL (W) / I
            if tipo == "Perfil (W) / I":
                col_w1, col_w2 = st.columns(2)
                with col_w1:
                    subtipo_w = st.selectbox("Modelo do Perfil", ["Perfil (W) I", "Perfil (W) H - HP", "Perfil I - Abas Inclinadas"], key="cad_sub_w")
                with col_w2:
                    mat_w = st.selectbox("Material", ["Aço Carbono (Padrão)", "Inox"], key="cad_mat_w")
                    
                sufixo_inox = " Inox" if mat_w == "Inox" else ""

                if subtipo_w == "Perfil (W) I":
                    col3, col4 = st.columns(2)
                    with col3:
                        alma_sel = st.selectbox("Alma", ["1ª Alma", "2ª Alma", "Outro"], key="cad_alma_wi")
                        if alma_sel == "Outro":
                            alma_custom = st.text_input("Nº da Alma", key="cad_alma_cust_wi")
                            alma_final = f"{alma_custom}ª Alma" if alma_custom else ""
                        else:
                            alma_final = alma_sel
                    with col4:
                        tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_wi")
                        
                    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                    with col_m1:
                        ext_val = st.text_input("Externo", key="cad_ext_wi")
                    with col_m2:
                        int_val = st.text_input("Interno", key="cad_int_wi")
                    with col_m3:
                        alt_val = st.text_input("Altura", key="cad_alt_wi")
                    with col_m4:
                        esp_alma_val = st.text_input("Espessura da alma", key="cad_espalma_wi")
                    with col_m5:
                        aba_val = st.text_input("Espessura da aba", key="cad_aba_wi")
                        
                    nome = f"Perfil (W) I{sufixo_inox}"
                    prefixo_alma = f"{alma_final} | " if alma_final else ""
                    dimensoes_para_salvar = f"{prefixo_alma}Ext: {ext_val} | Int: {int_val} | Alt: {alt_val} | Esp. Alma: {esp_alma_val} | Aba: {aba_val}"
                    unidade_para_salvar = tamanho
                    if not ext_val or not int_val or not alt_val or not esp_alma_val or not aba_val or (alma_sel == "Outro" and not alma_custom): campos_vazios = True

                elif subtipo_w == "Perfil (W) H - HP":
                    col3, col4, col5 = st.columns(3)
                    with col3:
                        modelo = st.selectbox("Especificação (W / HP)", ["W", "HP"], key="cad_mod_whp")
                    with col4:
                        alma_sel = st.selectbox("Alma", ["1ª Alma", "2ª Alma", "Outro"], key="cad_alma_whp")
                        if alma_sel == "Outro":
                            alma_custom = st.text_input("Nº da Alma", key="cad_alma_cust_whp")
                            alma_final = f"{alma_custom}ª Alma" if alma_custom else ""
                        else:
                            alma_final = alma_sel
                    with col5:
                        tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_whp")
                        
                    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                    with col_m1:
                        ext_val = st.text_input("Externo", key="cad_ext_whp")
                    with col_m2:
                        int_val = st.text_input("Interno", key="cad_int_whp")
                    with col_m3:
                        alt_val = st.text_input("Altura", key="cad_alt_whp")
                    with col_m4:
                        esp_alma_val = st.text_input("Espessura da alma", key="cad_espalma_whp")
                    with col_m5:
                        aba_val = st.text_input("Espessura da aba", key="cad_aba_whp")
                        
                    nome = f"Perfil {modelo}{sufixo_inox}"
                    prefixo_alma = f"{alma_final} | " if alma_final else ""
                    dimensoes_para_salvar = f"{prefixo_alma}Ext: {ext_val} | Int: {int_val} | Alt: {alt_val} | Esp. Alma: {esp_alma_val} | Aba: {aba_val}"
                    unidade_para_salvar = tamanho
                    if not ext_val or not int_val or not alt_val or not esp_alma_val or not aba_val or (alma_sel == "Outro" and not alma_custom): campos_vazios = True

                elif subtipo_w == "Perfil I - Abas Inclinadas":
                    col3, col4, col5, col6 = st.columns(4)
                    with col3:
                        modelo_sel = st.selectbox("Alma", ["Alma 1ª", "Alma 2ª", "Outro"], key="cad_mod_i_inc")
                        if modelo_sel == "Outro":
                            modelo_custom = st.text_input("Nº da Alma", key="cad_mod_cust_i_inc")
                            modelo = f"Alma {modelo_custom}ª" if modelo_custom else ""
                        else:
                            modelo = modelo_sel
                    with col4:
                        bit_h = st.text_input("Bitola h (Pol)", key="cad_h_i_inc")
                    with col5:
                        bit_b = st.text_input("Bitola b (Pol)", key="cad_b_i_inc")
                    with col6:
                        tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_i_inc")
                        
                    nome = f"Perfil I Abas Inclinadas{sufixo_inox}"
                    dim_h = bit_h.replace('"', '').strip()
                    dim_b = bit_b.replace('"', '').strip()
                    prefixo_modelo = f"{modelo} | " if modelo else ""
                    dimensoes_para_salvar = f'{prefixo_modelo}h: {dim_h}" x b: {dim_b}"'
                    unidade_para_salvar = tamanho
                    if not bit_h or not bit_b or (modelo_sel == "Outro" and not modelo_custom): campos_vazios = True

            # 2. GRUPO PERFIL U
            elif tipo == "Perfil U":
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    subtipo_u = st.selectbox("Modelo do Perfil U", ["U - Abas Inclinadas", "U - Simples", "U - Enrijecido"], key="cad_sub_u")
                with col_u2:
                    mat_u = st.selectbox("Material", ["Aço Carbono (Padrão)", "Inox"], key="cad_mat_u")
                    
                sufixo_inox = " Inox" if mat_u == "Inox" else ""

                if subtipo_u == "U - Abas Inclinadas":
                    col3, col4, col5, col6 = st.columns(4)
                    with col3:
                        modelo_sel = st.selectbox("Alma", ["Alma 1ª", "Alma 2ª", "Outro"], key="cad_mod_u_inc")
                        if modelo_sel == "Outro":
                            modelo_custom = st.text_input("Nº da Alma", key="cad_mod_cust_u_inc")
                            modelo = f"Alma {modelo_custom}ª" if modelo_custom else ""
                        else:
                            modelo = modelo_sel
                    with col4:
                        bit_h = st.text_input("Bitola h (Pol)", key="cad_h_u_inc")
                    with col5:
                        bit_b = st.text_input("Bitola b (Pol)", key="cad_b_u_inc")
                    with col6:
                        tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_u_inc")
                        
                    nome = f"Perfil U Abas Inclinadas{sufixo_inox}"
                    dim_h = bit_h.replace('"', '').strip()
                    dim_b = bit_b.replace('"', '').strip()
                    prefixo_modelo = f"{modelo} | " if modelo else ""
                    dimensoes_para_salvar = f'{prefixo_modelo}h: {dim_h}" x b: {dim_b}"'
                    unidade_para_salvar = tamanho
                    if not bit_h or not bit_b or (modelo_sel == "Outro" and not modelo_custom): campos_vazios = True

                elif subtipo_u == "U - Simples":
                    col3, col4, col5, col6 = st.columns(4)
                    with col3:
                        bit_h = st.text_input("Bitola h (mm)", key="cad_h_us")
                    with col4:
                        bit_b = st.text_input("Bitola b (mm)", key="cad_b_us")
                    with col5:
                        esp = st.text_input("Espessura (mm)", key="cad_esp_us")
                    with col6:
                        tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_us")
                        
                    nome = f"Perfil U Simples{sufixo_inox}"
                    dimensoes_para_salvar = f"h: {bit_h}mm x b: {bit_b}mm | Esp: {esp}mm"
                    unidade_para_salvar = tamanho
                    if not bit_h or not bit_b or not esp: campos_vazios = True

                elif subtipo_u == "U - Enrijecido":
                    col3, col4, col5, col6, col7 = st.columns(5)
                    with col3:
                        bit_h = st.text_input("Bitola h (mm)", key="cad_h_ue")
                    with col4:
                        bit_b = st.text_input("Bitola b (mm)", key="cad_b_ue")
                    with col5:
                        aba = st.text_input("Aba (mm)", key="cad_aba_ue")
                    with col6:
                        esp = st.text_input("Esp. (mm)", key="cad_esp_ue")
                    with col7:
                        tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_ue")
                        
                    nome = f"Perfil U Enrijecido{sufixo_inox}"
                    dimensoes_para_salvar = f"h: {bit_h} x b: {bit_b} x Aba: {aba} | Esp: {esp}mm"
                    unidade_para_salvar = tamanho
                    if not bit_h or not bit_b or not aba or not esp: campos_vazios = True

            # 3. GRUPO CANTONEIRA
            elif tipo in ["Cantoneira", "Cantoneira - Abas Iguais", "Cantoneira - Abas Desiguais"]:
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    indice_padrao = 1 if tipo == "Cantoneira - Abas Desiguais" else 0
                    subtipo_cant = st.selectbox("Modelo da Cantoneira", ["Abas Iguais", "Abas Desiguais"], index=indice_padrao, key="cad_sub_cant")
                with col_c2:
                    mat_cant = st.selectbox("Material", ["Aço Carbono (Padrão)", "Inox"], key="cad_mat_cant")

                sufixo_inox = " Inox" if mat_cant == "Inox" else ""

                if subtipo_cant == "Abas Iguais":
                    col3, col4, col5 = st.columns(3)
                    with col3:
                        bitola = st.text_input("Bitola (Pol)", key="cad_bit_cai")
                    with col4:
                        esp = st.text_input("Espessura (Pol)", key="cad_esp_cai")
                    with col5:
                        tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_cai")
                        
                    nome = f"Cantoneira Abas Iguais{sufixo_inox}"
                    dim1 = bitola.replace('"', '').strip()
                    dim2 = esp.replace('"', '').strip()
                    dimensoes_para_salvar = f'Bitola: {dim1}" | Esp: {dim2}"'
                    unidade_para_salvar = tamanho
                    if not bitola or not esp: campos_vazios = True
                else:
                    col3, col4, col5, col6 = st.columns(4)
                    with col3:
                        bit_h = st.text_input("Bitola h (Pol)", key="cad_h_cad")
                    with col4:
                        bit_b = st.text_input("Bitola b (Pol)", key="cad_b_cad")
                    with col5:
                        esp = st.text_input("Espessura (Pol)", key="cad_esp_cad")
                    with col6:
                        tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_cad")
                        
                    nome = f"Cantoneira Abas Desiguais{sufixo_inox}"
                    dim_h = bit_h.replace('"', '').strip()
                    dim_b = bit_b.replace('"', '').strip()
                    dim_esp = esp.replace('"', '').strip()
                    dimensoes_para_salvar = f'h: {dim_h}" x b: {dim_b}" | Esp: {dim_esp}"'
                    unidade_para_salvar = tamanho
                    if not bit_h or not bit_b or not esp: campos_vazios = True

            # 4. GRUPO BARRA
            elif tipo == "Barra":
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    subtipo_barra = st.selectbox("Formato da Barra", ["Barra Redonda", "Barra Quadrada", "Barra Sextavada", "Barra Chata"], key="cad_sub_barra")
                with col_b2:
                    mat_barra = st.selectbox("Material", ["Aço Carbono (Padrão)", "Inox"], key="cad_mat_barra")
                    
                sufixo_inox = " Inox" if mat_barra == "Inox" else ""

                if subtipo_barra in ["Barra Redonda", "Barra Quadrada", "Barra Sextavada"]:
                    col3, col4 = st.columns(2)
                    with col3:
                        bitola = st.text_input("Bitola (Pol)", key=f"cad_bit_{subtipo_barra.replace(' ', '_').lower()}")
                    with col4:
                        tamanho = st.selectbox("Tamanho", tamanho_opcoes, key=f"cad_tam_{subtipo_barra.replace(' ', '_').lower()}")
                        
                    nome = f"{subtipo_barra}{sufixo_inox}"
                    dim1 = bitola.replace('"', '').strip()
                    dimensoes_para_salvar = f'Bitola: {dim1}"'
                    unidade_para_salvar = tamanho
                    if not bitola: campos_vazios = True

                elif subtipo_barra == "Barra Chata":
                    col3, col4, col5 = st.columns(3)
                    with col3:
                        larg = st.text_input("Largura (Pol)", key="cad_larg_bc")
                    with col4:
                        esp = st.text_input("Espessura (Pol)", key="cad_esp_bc")
                    with col5:
                        tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_bc")
                        
                    nome = f"Barra Chata{sufixo_inox}"
                    dim1 = larg.replace('"', '').strip()
                    dim2 = esp.replace('"', '').strip()
                    dimensoes_para_salvar = f'Larg: {dim1}" | Esp: {dim2}"'
                    unidade_para_salvar = tamanho
                    if not larg or not esp: campos_vazios = True

        elif categoria == "CHAPAS E GRADES":
            nome = f"Chapa {tipo}" if "Piso" not in tipo and "Degraus" not in tipo else f"Grade {tipo}"
            
            if tipo in ["Fina Frio", "Fina Quente", "Inox"]:
                col3, col4, col5 = st.columns(3)
                with col3:
                    bitola = st.text_input("Bitola (mm)", key=f"cad_bit_{tipo[:4]}")
                with col4:
                    comp = st.text_input("Comprimento (mm)", key=f"cad_comp_{tipo[:4]}")
                with col5:
                    larg = st.text_input("Largura (mm)", key=f"cad_larg_{tipo[:4]}")
                    
                dimensoes_para_salvar = f"Bitola: {bitola}mm | {comp}mm x {larg}mm"
                if not bitola or not comp or not larg: campos_vazios = True

            elif tipo in ["Grossa", "Xadrez", "Zincada"]:
                col3, col4, col5 = st.columns(3)
                with col3:
                    esp = st.text_input("Espessura (Pol)", key=f"cad_esp_{tipo[:4]}")
                with col4:
                    comp = st.text_input("Comprimento (mm)", key=f"cad_comp_{tipo[:4]}")
                with col5:
                    larg = st.text_input("Largura (mm)", key=f"cad_larg_{tipo[:4]}")
                    
                dim1 = esp.replace('"', '').strip()
                dimensoes_para_salvar = f'Esp: {dim1}" | {comp}mm x {larg}mm'
                if not esp or not comp or not larg: campos_vazios = True

            elif tipo == "Perfurada - Furo Redondo":
                col3, col4, col5 = st.columns(3)
                with col3:
                    esp = st.text_input("Espessura (Pol)", key="cad_esp_perf")
                with col4:
                    comp = st.text_input("Comprimento (mm)", key="cad_comp_perf")
                with col5:
                    larg = st.text_input("Largura (mm)", key="cad_larg_perf")
                    
                col6, col7 = st.columns(2)
                with col6:
                    furo = st.text_input("Ø dos furos (Pol)", key="cad_furo_perf")
                with col7:
                    ec = st.text_input("E.C (mm)", key="cad_ec_perf")
                    
                dim1 = esp.replace('"', '').strip()
                dim2 = furo.replace('"', '').strip()
                dimensoes_para_salvar = f'Esp: {dim1}" | {comp}mm x {larg}mm | Furo: {dim2}" | E.C: {ec}mm'
                if not esp or not comp or not larg or not furo or not ec: campos_vazios = True

            elif tipo == "Expandida":
                col3, col4, col5, col6 = st.columns(4)
                with col3:
                    m_ld = st.text_input("Malha LD (mm)", key="cad_ld_exp")
                with col4:
                    m_cd = st.text_input("Malha CD (mm)", key="cad_cd_exp")
                with col5:
                    esp = st.text_input("Espessura (mm)", key="cad_esp_exp")
                with col6:
                    avanco = st.text_input("Avanço (mm)", key="cad_av_exp")
                    
                dimensoes_para_salvar = f"Malha: {m_ld}x{m_cd}mm | Esp: {esp}mm | Avanço: {avanco}mm"
                if not m_ld or not m_cd or not esp or not avanco: campos_vazios = True

            elif tipo in ["Piso Soldadas", "Piso Entrelaçadas"]:
                col3, col4, col5, col6 = st.columns(4)
                with col3:
                    tipo_grade = st.text_input("Tipo (Ex: XX-X0-000)", key=f"cad_tipo_{tipo[:6]}")
                with col4:
                    malha_b = st.text_input("Malha B (mm)", key=f"cad_mb_{tipo[:6]}")
                with col5:
                    malha_a = st.text_input("Malha A (mm)", key=f"cad_ma_{tipo[:6]}")
                with col6:
                    altura = st.text_input("Altura (mm)", key=f"cad_alt_{tipo[:6]}")
                    
                st.markdown("*Dados de Engenharia (Opcional)*")
                col7, col8 = st.columns(2)
                with col7:
                    vaos_opcoes = [str(v) for v in range(300, 2001 if tipo == "Piso Soldadas" else 1301, 100)]
                    vao = st.selectbox("Vão (mm)", vaos_opcoes, key=f"cad_vao_{tipo[:6]}")
                with col8:
                    opcoes_dados = ["C.U.D", "FLEXA"] 
                    dados = st.selectbox("Dados", opcoes_dados, key=f"cad_cud_{tipo[:6]}")
                            
                nome = f"Grade {tipo} {tipo_grade}"
                dimensoes_para_salvar = f"Malha: {malha_b}x{malha_a}mm | Alt: {altura}mm | Vão: {vao}mm | Dados: {dados}"
                        
                if not tipo_grade or not malha_b or not malha_a or not altura: campos_vazios = True

            elif tipo == "Degraus para Escadas":
                col3, col4, col5, col6, col7 = st.columns(5)
                with col3:
                    tipo_degrau = st.text_input("Tipo (Ex: XX-00/0)", key="cad_tipo_deg")
                with col4:
                    comp = st.text_input("Comp. (mm)", key="cad_comp_deg")
                with col5:
                    larg = st.text_input("Larg. (mm)", key="cad_larg_deg")
                with col6:
                    alt = st.text_input("Alt. (mm)", key="cad_alt_deg")
                with col7:
                    esp = st.text_input("Esp. (mm)", key="cad_esp_deg")
                    
                nome = f"Degrau p/ Escada {tipo_degrau}"
                dimensoes_para_salvar = f"{comp}x{larg}mm | Alt: {alt}mm | Esp: {esp}mm"
                if not tipo_degrau or not comp or not larg or not alt or not esp: campos_vazios = True

        elif categoria == "CONSTRUÇÃO CIVIL":
            if tipo in ["Vergalhões CA - 25", "Vergalhões CA - 50"]:
                col3, col4 = st.columns(2)
                with col3:
                    bitola = st.text_input("Bitola (Pol)", key=f"cad_bit_v_{tipo[-2:]}")
                with col4:
                    comp = st.text_input("Comprimento (m)", key=f"cad_comp_v_{tipo[-2:]}")
                    
                nome = f"{tipo}"
                dim1 = bitola.replace('"', '').strip()
                dimensoes_para_salvar = f'Bitola: {dim1}" | Comp: {comp}m'
                if not bitola or not comp: campos_vazios = True

            elif tipo == "Vergalhões CA - 60":
                col3, col4 = st.columns(2)
                with col3:
                    bitola = st.text_input("Bitola (mm)", key="cad_bit_v_60")
                with col4:
                    comp = st.text_input("Comprimento (m)", key="cad_comp_v_60")
                    
                nome = f"{tipo}"
                dimensoes_para_salvar = f"Bitola: {bitola}mm | Comp: {comp}m"
                if not bitola or not comp: campos_vazios = True

            elif tipo == "Arame Recozido":
                col3, col4, col5 = st.columns(3)
                with col3:
                    bmg = st.text_input("BMG / BWG N°", key="cad_bmg_ar")
                with col4:
                    diam = st.text_input("Diâmetro (mm)", key="cad_diam_ar")
                with col5:
                    comp = st.text_input("Comprimento (m)", key="cad_comp_ar")
                    
                nome = f"{tipo}"
                dimensoes_para_salvar = f"BMG: {bmg} | Ø: {diam}mm | Comp: {comp}m"
                if not bmg or not diam or not comp: campos_vazios = True

            elif tipo == "Barra de Transferência":
                col3, col4 = st.columns(2)
                with col3:
                    bitola = st.text_input("Bitola (mm)", key="cad_bit_bt")
                with col4:
                    comp = st.text_input("Comprimento (m)", key="cad_comp_bt")
                    
                nome = f"{tipo}"
                dimensoes_para_salvar = f"Bitola: {bitola}mm | Comp: {comp}m"
                if not bitola or not comp: campos_vazios = True

            elif tipo == "Tela Soldada Nervurada":
                ref = st.text_input("REF. (Ex: Q 138)", key="cad_ref_tsn")
                nome = f"{tipo}"
                dimensoes_para_salvar = f"REF: {ref}"
                if not ref: campos_vazios = True

            elif tipo == "Telha":
                col3, col4, col5, col6 = st.columns(4)
                with col3:
                    modelo = st.selectbox("Modelo", ["Trapezoidal", "Galvalume", "Zinco", "Sanduíche"], key="cad_mod_telha")
                with col4:
                    esp = st.selectbox("Espessura (mm)", ["0,43", "0,5", "0,65"], key="cad_esp_telha")
                with col5:
                    apoio = st.selectbox("Distância entre apoios (mm)", ["2000", "2500", "2750"], key="cad_apoio_telha")
                with col6:
                    comp = st.text_input("Comprimento (m)", key="cad_comp_telha")
                    
                nome = f"Telha {modelo}"
                dimensoes_para_salvar = f"Esp: {esp}mm | Apoio: {apoio}mm | Comp: {comp}m"
                if not comp: campos_vazios = True

            elif tipo == "Treliça":
                col3, col4, col5, col6 = st.columns(4)
                with col3:
                    altura = st.text_input("Altura (cm)", key="cad_alt_trel")
                with col4:
                    banzo_sup = st.text_input("Banzo Sup. (mm)", key="cad_bsup_trel")
                with col5:
                    diagonal = st.text_input("Diagonal (mm)", key="cad_diag_trel")
                with col6:
                    banzo_inf = st.text_input("Banzo Inf. (mm)", key="cad_binf_trel")
                    
                nome = f"{tipo}"
                dimensoes_para_salvar = f"Alt: {altura}cm | Banzos/Diag: {banzo_sup} x {diagonal} x {banzo_inf} mm"
                
                if not altura or not banzo_sup or not diagonal or not banzo_inf: campos_vazios = True

        st.markdown("**Estoque Inicial (Peças Físicas)**")
        quantidade = st.number_input("Quantidade", min_value=0, step=1, key="quantidade")
            
        submit_button = st.button(label='Salvar no Banco de Dados', type="primary")

        if submit_button:
            nome_limpo = nome.strip().upper()
            dimensoes_limpas = dimensoes_para_salvar.strip().upper()
            cod_final = codigo.strip().upper() if codigo else "-"
            
            valor_kg_limpo = re.sub(r'[^0-9,]', '', valor_kg) if valor_kg else "-"
            if not valor_kg_limpo: 
                valor_kg_limpo = "-"
                
            # Tratamento da Origem e Tributação (salva vazio "" se não preenchido)
            orig_pct_limpo = re.sub(r'[^0-9,]', '', origem_pct) if origem_pct else ""
            if origem_tipo == "Não informar":
                origem_final = ""
            else:
                origem_final = f"{origem_tipo.upper()} ({orig_pct_limpo}%)" if orig_pct_limpo else origem_tipo.upper()
                
            st_limpo = re.sub(r'[^0-9,]', '', st_val) if st_val else ""
            difal_limpo = re.sub(r'[^0-9,]', '', difal_val) if difal_val else ""
            icms_limpo = re.sub(r'[^0-9,]', '', icms_val) if icms_val else ""
            
            if campos_vazios:
                st.warning("⚠️ Por favor, preencha todos os campos obrigatórios da peça!")
            elif codigo_em_uso:
                st.error("❌ O código digitado já pertence a outro material. Apague ou altere o código para prosseguir.")
            else:
                dimensoes_sem_espaco = dimensoes_limpas.replace(" ", "")
                
                c.execute('''
                    SELECT id FROM materiais 
                    WHERE categoria = %s AND nome = %s 
                    AND REPLACE(dimensoes, ' ', '') = %s AND filial = %s
                ''', (categoria, nome_limpo, dimensoes_sem_espaco, filial_selecionada))
                
                if c.fetchone():
                    st.error(f"❌ Cadastro Bloqueado (Segurança Ativada): O material '{nome_limpo}' com essas dimensões exatas já existe na filial {filial_selecionada}!")
                else:
                    c.execute('''
                        INSERT INTO materiais (codigo, categoria, tipo, nome, dimensoes, unidade, saldo, filial, valor_kg, origem, st, difal, icms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (cod_final, categoria, tipo, nome_limpo, dimensoes_limpas, unidade_para_salvar, quantidade, filial_selecionada, valor_kg_limpo, origem_final, st_limpo, difal_limpo, icms_limpo))
                    
                    c.execute('''
                        INSERT INTO historico_movimentacao (data_hora, usuario, categoria, tipo, nome, dimensoes, unidade, operacao, quantidade)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (obter_agora_br(), st.session_state['usuario_nome'], categoria, tipo, nome_limpo, dimensoes_limpas, unidade_para_salvar, 'CADASTRO', quantidade))
                    
                    conn.commit()
                    st.success(f"✅ Material '{nome_limpo}' cadastrado com sucesso!")
                    st.rerun()

        exibir_historico_operacoes()

    with aba_movimentacao:
        st.subheader("🔄 Movimentação de Estoque")

        c.execute("SELECT id, codigo, categoria, tipo, nome, dimensoes, saldo, unidade, filial, valor_kg, origem, st, difal, icms FROM materiais")
        df_materiais = pd.DataFrame(c.fetchall(), columns=["id", "codigo", "categoria", "tipo", "nome", "dimensoes", "saldo", "unidade", "filial", "valor_kg", "origem", "st", "difal", "icms"])

        if df_materiais.empty:
            st.info("💡 Cadastre pelo menos um material no formulário acima para poder realizar movimentações.")
        else:
            df_materiais['identificador'] = df_materiais.apply(montar_identificador, axis=1)

            st.markdown("**1. Localize o Material**")
            modo_busca = st.radio(
                "Escolha como quer localizar a peça:", 
                ["🔍 Busca Rápida (Digitar Código ou Nome)", "🗂️ Procurar por Categoria (Catálogo)"], 
                horizontal=True
            )

            df_final = pd.DataFrame()
            item_selecionado = None

            if modo_busca == "🔍 Busca Rápida (Digitar Código ou Nome)":
                st.info("💡 Dica: Clique na caixa abaixo e comece a digitar o Código ou o Nome. A lista vai filtrar automaticamente!")
                item_selecionado = st.selectbox("Digite ou selecione a peça:", df_materiais['identificador'].tolist(), key="mov_item_rapido")
                df_final = df_materiais

            else:
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    categorias_existentes = df_materiais['categoria'].unique()
                    filtro_cat = st.selectbox("Categoria:", categorias_existentes, key="mov_cat")
                    
                with col_m2:
                    df_filtrado_cat = df_materiais[df_materiais['categoria'] == filtro_cat]
                    tipos_existentes = df_filtrado_cat['tipo'].unique()
                    filtro_tipo = st.selectbox("Grupo / Tipo:", tipos_existentes, key="mov_tipo")

                df_filtrado_tipo = df_filtrado_cat[df_filtrado_cat['tipo'] == filtro_tipo].copy()

                if filtro_cat == "FLANGES":
                    if filtro_tipo == "ANSI" and not df_filtrado_tipo.empty:
                        col_m3, col_m4 = st.columns(2)
                        with col_m3:
                            classes_possiveis = ["150 LBS", "300 LBS", "400 LBS", "600 LBS", "900 LBS", "1500 LBS"]
                            classes_existentes = [c for c in classes_possiveis if df_filtrado_tipo['nome'].str.contains(c, case=False, regex=False).any()]
                            filtro_classe = st.selectbox("Classe:", classes_existentes if classes_existentes else ["Nenhuma"], key="mov_classe_ansi")
                            if filtro_classe != "Nenhuma":
                                df_filtrado_tipo = df_filtrado_tipo[df_filtrado_tipo['nome'].str.contains(filtro_classe, case=False, regex=False)]
                                
                        with col_m4:
                            modelos_possiveis = ["WN (Weld-Neck)", "SW (Socket-Weld)", "CEGO", "SOB PLANO", "SO (Slip-on)", "SOLTO"]
                            modelos_existentes = [m for m in modelos_possiveis if df_filtrado_tipo['nome'].str.contains(m, case=False, regex=False).any()]
                            filtro_modelo = st.selectbox("Modelo:", modelos_existentes if modelos_existentes else ["Nenhum"], key="mov_modelo_ansi")
                            if filtro_modelo != "Nenhum":
                                df_filtrado_tipo = df_filtrado_tipo[df_filtrado_tipo['nome'].str.contains(filtro_modelo, case=False, regex=False)]

                    elif filtro_tipo == "AWWA C-207" and not df_filtrado_tipo.empty:
                        classes_possiveis = ["CLASSE B  (86 PSI)", "CLASSE D (175 : 150 PSI)", "CLASSE E  (275 PSI)", "CLASSE F  (300 PSI)"]
                        classes_existentes = [c for c in classes_possiveis if df_filtrado_tipo['nome'].str.upper().str.contains(c, case=False, regex=False).any()]
                        filtro_classe = st.selectbox("Classe:", classes_existentes if classes_existentes else ["Nenhuma"], key="mov_classe_awwa")
                        if filtro_classe != "Nenhuma":
                            df_filtrado_tipo = df_filtrado_tipo[df_filtrado_tipo['nome'].str.upper().str.contains(filtro_classe, case=False, regex=False)]

                    elif filtro_tipo == "PN" and not df_filtrado_tipo.empty:
                        col_m3, col_m4 = st.columns(2)
                        with col_m3:
                            pn_possiveis = ["PN 10", "PN 16", "PN 25", "PN 40", "PN 63", "PN 100"]
                            pn_existentes = [p for p in pn_possiveis if df_filtrado_tipo['nome'].str.contains(p, case=False, regex=False).any()]
                            filtro_pn = st.selectbox("Pressão (PN):", pn_existentes if pn_existentes else ["Nenhuma"], key="mov_pn_val")
                            if filtro_pn != "Nenhuma":
                                df_filtrado_tipo = df_filtrado_tipo[df_filtrado_tipo['nome'].str.contains(filtro_pn, case=False, regex=False)]
                                
                        with col_m4:
                            classes_pn_possiveis = ["Tipo 1", "Tipo 2", "Tipo 5", "Tipo 11", "Tipo 12"]
                            classes_pn_existentes = [c for c in classes_pn_possiveis if df_filtrado_tipo['nome'].str.contains(c, case=False, regex=False).any()]
                            filtro_classe_pn = st.selectbox("Classe:", classes_pn_existentes if classes_pn_existentes else ["Nenhuma"], key="mov_classe_pn")
                            if filtro_classe_pn != "Nenhuma":
                                df_filtrado_tipo = df_filtrado_tipo[df_filtrado_tipo['nome'].str.contains(filtro_classe_pn, case=False, regex=False)]

                elif filtro_cat != "FLANGES" and not df_filtrado_tipo.empty:
                    nomes_existentes = df_filtrado_tipo['nome'].unique().tolist()
                    filtro_modelo_dinamico = st.selectbox("Modelo / Especificação:", ["Todos"] + nomes_existentes, key="mov_mod_dinamico")
                    if filtro_modelo_dinamico != "Todos":
                        df_filtrado_tipo = df_filtrado_tipo[df_filtrado_tipo['nome'] == filtro_modelo_dinamico]

                df_final = df_filtrado_tipo.copy()
                
                if not df_final.empty:
                    item_selecionado = st.selectbox("Peça Exata:", df_final['identificador'].tolist(), key="mov_item_filtro")

            if item_selecionado and not df_final.empty:
                st.markdown("**2. Detalhes e Operação**")
                
                col_op2, col_op3 = st.columns(2)
                with col_op2:
                    operacao = st.radio("Operação:", ["Entrada (Soma)", "Saída (Subtrai)"], key="mov_op")
                with col_op3:
                    quantidade = st.number_input("Quantidade:", min_value=1, step=1, key="mov_qtd")
                    
                linha_selecionada = df_final[df_final['identificador'] == item_selecionado]
                id_real = int(linha_selecionada['id'].values[0])
                saldo_atual = float(linha_selecionada['saldo'].values[0])
                nome_real = f"{linha_selecionada['nome'].values[0]} {linha_selecionada['dimensoes'].values[0]}"
                
                btn_movimentar = st.button("Confirmar Movimentação", use_container_width=True, type="primary")
                
                if btn_movimentar:
                    op_log = 'ENTRADA' if operacao == "Entrada (Soma)" else 'SAÍDA'
                    if operacao == "Entrada (Soma)":
                        novo_saldo = saldo_atual + quantidade
                        msg = f"🚀 Entrada de {quantidade} unidades de '{nome_real}' realizada com sucesso!"
                    else:
                        novo_saldo = saldo_atual - quantidade
                        msg = f"📉 Saída de {quantidade} unidades de '{nome_real}' realizada com sucesso!"
                    
                    if novo_saldo < 0:
                        st.error(f"❌ Erro: Saldo insuficiente. O estoque atual é de apenas {int(saldo_atual)}.")
                    else:
                        c.execute("UPDATE materiais SET saldo = %s WHERE id = %s", (novo_saldo, id_real))
                        
                        c.execute('''
                            INSERT INTO historico_movimentacao (data_hora, usuario, categoria, tipo, nome, dimensoes, unidade, operacao, quantidade)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ''', (obter_agora_br(), st.session_state['usuario_nome'], linha_selecionada['categoria'].values[0], linha_selecionada['tipo'].values[0], linha_selecionada['nome'].values[0], linha_selecionada['dimensoes'].values[0], linha_selecionada['unidade'].values[0], op_log, quantidade))
                        
                        conn.commit()
                        st.success(msg)
                        st.rerun()
            elif df_final.empty:
                st.warning("⚠️ Nenhum material encontrado no estoque com esses filtros.")

        exibir_historico_operacoes()

    # --- ABA DE INVENTÁRIO (PCP) ---
    with aba_inventario:
        st.subheader("📋 Planilha de Inventário Dinâmica")
        
        c.execute("SELECT id, codigo, filial, categoria, nome, dimensoes, unidade, saldo, valor_kg, origem, st, difal, icms FROM materiais ORDER BY nome")
        df_estoque = pd.DataFrame(c.fetchall(), columns=["id", "Código", "Aços Vital", "Categoria", "Tipo", "Dimensões", "UNID", "Saldo", "Valor / kg", "Origem", "st", "difal", "icms"])
        
        if df_estoque.empty:
            st.info("O estoque está vazio.")
        else:
            df_estoque.fillna("", inplace=True)
            df_estoque["ST (%) | DIFAL (%) | ICMS (%)"] = df_estoque.apply(formatar_tributacao_unificada, axis=1)
            
            # --- BARRA DE FILTROS DO INVENTÁRIO (PCP) ---
            st.markdown("##### 🔍 Filtrar Inventário")
            col_f1, col_f2, col_f3, col_f4 = st.columns([1, 1.5, 1.8, 1.5])
            
            with col_f1:
                filiais_disp = ["Todas"] + sorted([f for f in df_estoque["Aços Vital"].unique().tolist() if f])
                f_filial = st.selectbox("Filial (Aços Vital):", filiais_disp, key="inv_pcp_filial")
                
            df_temp = df_estoque if f_filial == "Todas" else df_estoque[df_estoque["Aços Vital"] == f_filial]
            
            with col_f2:
                cats_disp = ["Todas"] + sorted([cat for cat in df_temp["Categoria"].unique().tolist() if cat])
                f_cat = st.selectbox("Categoria:", cats_disp, key="inv_pcp_cat")
                
            df_temp2 = df_temp if f_cat == "Todas" else df_temp[df_temp["Categoria"] == f_cat]
            
            with col_f3:
                tipos_disp = ["Todos"] + sorted([t for t in df_temp2["Tipo"].unique().tolist() if t])
                f_tipo = st.selectbox("Tipo:", tipos_disp, key="inv_pcp_tipo")
                
            with col_f4:
                f_busca = st.text_input("Buscar Código ou Medida:", placeholder="Digite para filtrar...", key="inv_pcp_busca")
                
            df_filtrado_inv = df_temp2 if f_tipo == "Todos" else df_temp2[df_temp2["Tipo"] == f_tipo]
            if f_busca:
                termo = f_busca.strip()
                df_filtrado_inv = df_filtrado_inv[
                    df_filtrado_inv["Código"].astype(str).str.contains(termo, case=False, na=False) |
                    df_filtrado_inv["Tipo"].astype(str).str.contains(termo, case=False, na=False) |
                    df_filtrado_inv["Dimensões"].astype(str).str.contains(termo, case=False, na=False)
                ]
            df_filtrado_inv = df_filtrado_inv.reset_index(drop=True)
            
            st.info("💡 **Edição Rápida PCP:** Dê um duplo-clique nas células de **Código**, **Dimensões**, **Valor / kg**, **Origem** ou **ST (%) | DIFAL (%) | ICMS (%)** (Ex: `ST: 18% | ICMS: 12%`) para editar, e depois clique em Salvar abaixo.")
            
            edited_df = st.data_editor(
                df_filtrado_inv,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "id": None,
                    "st": None,
                    "difal": None,
                    "icms": None,
                    "Código": st.column_config.TextColumn("Código", width="small"),
                    "Aços Vital": st.column_config.TextColumn("Aços Vital", width="small"),
                    "Categoria": st.column_config.TextColumn("Categoria", width="medium"),
                    "Tipo": st.column_config.TextColumn("Tipo", width="large"),
                    "Dimensões": st.column_config.TextColumn("Dimensões", width="large"),
                    "UNID": st.column_config.TextColumn("UNID", width="small"),
                    "Saldo": st.column_config.NumberColumn("Saldo", width="small"),
                    "Valor / kg": st.column_config.TextColumn("Valor / kg", width="small"),
                    "Origem": st.column_config.TextColumn("Origem", width="medium", help="Ex: NACIONAL (12%) ou IMPORTADO (4%)"),
                    "ST (%) | DIFAL (%) | ICMS (%)": st.column_config.TextColumn("ST (%) | DIFAL (%) | ICMS (%)", width="medium", help="Ex: ST: 18% | DIFAL: 6% | ICMS: 12%")
                },
                disabled=["Aços Vital", "Categoria", "Tipo", "UNID", "Saldo"],
                key="editor_inventario"
            )
            
            if st.button("💾 Salvar Alterações na Planilha", type="primary", use_container_width=True):
                alteracoes = st.session_state["editor_inventario"]["edited_rows"]
                if alteracoes:
                    for row_idx, col_alteradas in alteracoes.items():
                        db_id = int(df_filtrado_inv.loc[row_idx, "id"])
                        st_atual = str(df_filtrado_inv.loc[row_idx, "st"])
                        difal_atual = str(df_filtrado_inv.loc[row_idx, "difal"])
                        icms_atual = str(df_filtrado_inv.loc[row_idx, "icms"])
                        
                        c.execute("SELECT categoria, tipo, nome, dimensoes, unidade FROM materiais WHERE id = %s", (db_id,))
                        mat_info = c.fetchone()
                        
                        if "Código" in col_alteradas:
                            novo_codigo = col_alteradas["Código"]
                            novo_codigo = str(novo_codigo).strip().upper() if novo_codigo else "-"
                            c.execute("UPDATE materiais SET codigo = %s WHERE id = %s", (novo_codigo, db_id))

                        if "Dimensões" in col_alteradas:
                            nova_dim = col_alteradas["Dimensões"]
                            nova_dim = str(nova_dim).strip().upper() if nova_dim else "-"
                            c.execute("UPDATE materiais SET dimensoes = %s WHERE id = %s", (nova_dim, db_id))
                            
                        if "Valor / kg" in col_alteradas:
                            novo_valor = col_alteradas["Valor / kg"]
                            novo_valor = re.sub(r'[^0-9,]', '', str(novo_valor)) if novo_valor else "-"
                            c.execute("UPDATE materiais SET valor_kg = %s WHERE id = %s", (novo_valor, db_id))

                        if "Origem" in col_alteradas:
                            nova_orig = col_alteradas["Origem"]
                            nova_orig = str(nova_orig).strip().upper() if nova_orig else ""
                            c.execute("UPDATE materiais SET origem = %s WHERE id = %s", (nova_orig, db_id))

                        if "ST (%) | DIFAL (%) | ICMS (%)" in col_alteradas:
                            texto_trib = col_alteradas["ST (%) | DIFAL (%) | ICMS (%)"]
                            n_st, n_dif, n_icm = extrair_impostos_da_coluna(texto_trib, st_atual, difal_atual, icms_atual)
                            c.execute("UPDATE materiais SET st = %s, difal = %s, icms = %s WHERE id = %s", (n_st, n_dif, n_icm, db_id))
                            
                        c.execute('''
                            INSERT INTO historico_movimentacao (data_hora, usuario, categoria, tipo, nome, dimensoes, unidade, operacao, quantidade)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ''', (obter_agora_br(), st.session_state['usuario_nome'], mat_info[0], mat_info[1], mat_info[2], mat_info[3], mat_info[4], 'EDIÇÃO', 0))
                            
                    conn.commit()
                    st.success("✅ Alterações salvas com sucesso no banco de dados!")
                    st.rerun()
                else:
                    st.info("💡 Nenhuma alteração foi realizada para ser salva.")
            
            st.markdown("---")
            st.subheader("🗑️ Excluir Cadastro de Material")
            st.warning("⚠️ Atenção: Esta ação apagará o material e seu saldo do banco de dados definitivamente. Utilize para corrigir erros de cadastro.")
            
            df_estoque['identificador_exclusao'] = df_estoque.apply(
                lambda r: f"[{r['Código']}] {r['Tipo']} - {r['Dimensões']} | {r['Aços Vital']} | Saldo: {int(r['Saldo'])} {r['UNID']}" if r['Código'] and r['Código'] != "-" else f"{r['Tipo']} - {r['Dimensões']} | {r['Aços Vital']} | Saldo: {int(r['Saldo'])} {r['UNID']}", axis=1
            )
            
            item_excluir = st.selectbox("Selecione o material que deseja excluir:", [""] + df_estoque['identificador_exclusao'].tolist(), key="select_excluir")
            
            if item_excluir != "":
                linha_del = df_estoque[df_estoque['identificador_exclusao'] == item_excluir]
                id_del = int(linha_del['id'].values[0])
                
                c.execute("SELECT categoria, tipo, nome, dimensoes, unidade, saldo FROM materiais WHERE id = %s", (id_del,))
                mat_info = c.fetchone()
                nome_del = f"{mat_info[2]} {mat_info[3]}"
                
                if st.button(f"🚨 Confirmar Exclusão: {nome_del}", use_container_width=True):
                    c.execute('''
                        INSERT INTO historico_movimentacao (data_hora, usuario, categoria, tipo, nome, dimensoes, unidade, operacao, quantidade)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (obter_agora_br(), st.session_state['usuario_nome'], mat_info[0], mat_info[1], mat_info[2], mat_info[3], mat_info[4], 'EXCLUSÃO', mat_info[5]))
                    
                    c.execute("DELETE FROM materiais WHERE id = %s", (id_del,))
                    conn.commit()
                    st.success(f"✅ Material '{nome_del}' removido do catálogo com sucesso!")
                    st.rerun()

        exibir_historico_operacoes()

# ==========================================
# SE FOR VENDEDOR / COMPRAS: Visualização de Leitura com Filtros
# ==========================================
elif st.session_state['perfil'] == "VENDEDOR":
    st.subheader("📋 Inventário Atualizado em Tempo Real")
    c.execute("SELECT codigo, filial, categoria, nome, dimensoes, unidade, saldo, valor_kg, origem, st, difal, icms FROM materiais ORDER BY nome")
    df_estoque = pd.DataFrame(c.fetchall(), columns=["Código", "Aços Vital", "Categoria", "Tipo", "Dimensões", "UNID", "Saldo", "Valor / kg", "Origem", "st", "difal", "icms"])
    
    if df_estoque.empty:
        st.info("O estoque está vazio no momento.")
    else:
        df_estoque.fillna("", inplace=True)
        df_estoque["ST (%) | DIFAL (%) | ICMS (%)"] = df_estoque.apply(formatar_tributacao_unificada, axis=1)
        
        # Remove as colunas brutas st/difal/icms da visualização de vendas, mantendo apenas a coluna unificada
        df_estoque_view = df_estoque[["Código", "Aços Vital", "Categoria", "Tipo", "Dimensões", "UNID", "Saldo", "Valor / kg", "Origem", "ST (%) | DIFAL (%) | ICMS (%)"]].copy()
        
        # --- BARRA DE FILTROS DO INVENTÁRIO (VENDEDOR / COMPRAS) ---
        st.markdown("##### 🔍 Filtrar Inventário")
        col_f1, col_f2, col_f3, col_f4 = st.columns([1, 1.5, 1.8, 1.5])
        
        with col_f1:
            filiais_disp = ["Todas"] + sorted([f for f in df_estoque_view["Aços Vital"].unique().tolist() if f])
            f_filial = st.selectbox("Filial (Aços Vital):", filiais_disp, key="inv_vend_filial")
            
        df_temp = df_estoque_view if f_filial == "Todas" else df_estoque_view[df_estoque_view["Aços Vital"] == f_filial]
        
        with col_f2:
            cats_disp = ["Todas"] + sorted([cat for cat in df_temp["Categoria"].unique().tolist() if cat])
            f_cat = st.selectbox("Categoria:", cats_disp, key="inv_vend_cat")
            
        df_temp2 = df_temp if f_cat == "Todas" else df_temp[df_temp["Categoria"] == f_cat]
        
        with col_f3:
            tipos_disp = ["Todos"] + sorted([t for t in df_temp2["Tipo"].unique().tolist() if t])
            f_tipo = st.selectbox("Tipo:", tipos_disp, key="inv_vend_tipo")
            
        with col_f4:
            f_busca = st.text_input("Buscar Código ou Medida:", placeholder="Digite para filtrar...", key="inv_vend_busca")
            
        df_filtrado_vend = df_temp2 if f_tipo == "Todos" else df_temp2[df_temp2["Tipo"] == f_tipo]
        if f_busca:
            termo = f_busca.strip()
            df_filtrado_vend = df_filtrado_vend[
                df_filtrado_vend["Código"].astype(str).str.contains(termo, case=False, na=False) |
                df_filtrado_vend["Tipo"].astype(str).str.contains(termo, case=False, na=False) |
                df_filtrado_vend["Dimensões"].astype(str).str.contains(termo, case=False, na=False)
            ]
        df_filtrado_vend = df_filtrado_vend.reset_index(drop=True)
        
        config_vendedor = {
            "Código": st.column_config.TextColumn("Código", width="small"),
            "Aços Vital": st.column_config.TextColumn("Aços Vital", width="small"),
            "Categoria": st.column_config.TextColumn("Categoria", width="medium"),
            "Tipo": st.column_config.TextColumn("Tipo", width="large"),
            "Dimensões": st.column_config.TextColumn("Dimensões", width="large"),
            "UNID": st.column_config.TextColumn("UNID", width="small"),
            "Saldo": st.column_config.NumberColumn("Saldo", width="small"),
            "Valor / kg": st.column_config.TextColumn("Valor / kg", width="small"),
            "Origem": st.column_config.TextColumn("Origem", width="medium"),
            "ST (%) | DIFAL (%) | ICMS (%)": st.column_config.TextColumn("ST (%) | DIFAL (%) | ICMS (%)", width="medium"),
        }
        
        st.dataframe(
            df_filtrado_vend, 
            use_container_width=True, 
            hide_index=True,
            column_config=config_vendedor
        )
    exibir_historico_operacoes()
